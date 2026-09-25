"""Citizen signals («Народный контроль»): creation, geo-binding, deduplication, lifecycle."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2 import Geography
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import Select, cast, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError, RateLimitedError, ValidationFailedError
from app.db.models import Parcel, Photo, Signal, TelegramUser
from app.domain.enums import (
    SIGNAL_CATEGORY_TO_VIOLATION,
    EntityType,
    EventType,
    Lang,
    ParcelStatus,
    PhotoOwnerType,
    PhotoSource,
    SignalCategory,
    SignalStatus,
)
from app.domain.state_machine import allowed_transitions, can_transition, ensure_transition
from app.domain.tracking import format_signal_code
from app.providers.storage import StorageProvider
from app.schemas.signals import SignalDetail, SignalList, SignalSummary, SignalTransitionRequest
from app.services import audit, notifier
from app.services.parcels import apply_transition, get_parcel
from app.services.photos import PhotoSpec, photos_for, save_photos

PARCEL_SEARCH_RADIUS_M = 100
DUPLICATE_RADIUS_M = 30
DUPLICATE_WINDOW = timedelta(days=7)
OPEN_STATUSES = (SignalStatus.NEW, SignalStatus.IN_REVIEW)
SYSTEM_ACTOR = "system"


@dataclass(slots=True)
class ParcelMatch:
    parcel_id: uuid.UUID
    distance_m: float


def in_region(lat: float, lon: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = get_settings().region_bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _point(lat: float, lon: float) -> Any:
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)


async def find_parcel(session: AsyncSession, lat: float, lon: float) -> ParcelMatch | None:
    """Parcel containing the point, otherwise the nearest one within 100 m."""
    point = _point(lat, lon)
    contained = await session.scalar(
        select(Parcel.id).where(func.ST_Contains(Parcel.geometry, point)).limit(1)
    )
    if contained is not None:
        return ParcelMatch(parcel_id=contained, distance_m=0.0)
    geo_point = cast(point, Geography)
    geo_parcel = cast(Parcel.geometry, Geography)
    row = (
        await session.execute(
            select(Parcel.id, func.ST_Distance(geo_parcel, geo_point).label("distance"))
            .where(func.ST_DWithin(geo_parcel, geo_point, PARCEL_SEARCH_RADIUS_M))
            .order_by(text("distance"))
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return ParcelMatch(parcel_id=row[0], distance_m=round(float(row[1]), 1))


async def find_duplicate_root(
    session: AsyncSession, lat: float, lon: float, now: datetime
) -> uuid.UUID | None:
    """Earliest non-rejected root signal within 30 m during the last 7 days."""
    geo_point = cast(_point(lat, lon), Geography)
    return await session.scalar(
        select(Signal.id)
        .where(
            Signal.duplicate_of.is_(None),
            Signal.status != SignalStatus.REJECTED,
            Signal.created_at >= now - DUPLICATE_WINDOW,
            func.ST_DWithin(cast(Signal.location, Geography), geo_point, DUPLICATE_RADIUS_M),
        )
        .order_by(Signal.created_at)
        .limit(1)
    )


async def signals_in_last_hour(session: AsyncSession, chat_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(Signal.id)).where(
                Signal.reporter_chat_id == chat_id,
                Signal.created_at >= datetime.now(UTC) - timedelta(hours=1),
            )
        )
        or 0
    )


async def check_rate_limit(session: AsyncSession, chat_id: int) -> None:
    limit = get_settings().signals_per_hour_limit
    if await signals_in_last_hour(session, chat_id) >= limit:
        raise RateLimitedError("Too many signals, try again later", details={"limit_per_hour": limit})


async def create_signal(
    session: AsyncSession,
    *,
    lat: float,
    lon: float,
    category: SignalCategory,
    description: str | None,
    reporter_chat_id: int | None,
    reporter_lang: Lang,
    address: str | None = None,
    actor: str | None = None,
    enforce_rate_limit: bool = True,
) -> Signal:
    """Create a signal, bind it to a parcel, deduplicate and flag the parcel for checking.

    Photos are attached separately with :func:`attach_photos` so the bot can answer
    the citizen immediately and download files in the background.
    """
    if not in_region(lat, lon):
        raise ValidationFailedError("Location is outside the service region", code="OUT_OF_REGION")
    if description is not None:
        description = description.strip()[:500] or None
    if reporter_chat_id is not None and enforce_rate_limit:
        await check_rate_limit(session, reporter_chat_id)

    now = datetime.now(UTC)
    seq = int(await session.scalar(select(func.nextval("signal_tracking_seq"))) or 0)
    code = format_signal_code(now.year, seq)
    match = await find_parcel(session, lat, lon)
    duplicate_root = await find_duplicate_root(session, lat, lon, now)
    actor = actor or (f"citizen:{reporter_chat_id}" if reporter_chat_id else SYSTEM_ACTOR)

    signal = Signal(
        tracking_code=code,
        location=from_shape(Point(lon, lat), srid=4326),
        category=category,
        description=description,
        address=address,
        status=SignalStatus.NEW,
        parcel_id=match.parcel_id if match else None,
        parcel_distance_m=match.distance_m if match else None,
        duplicate_of=duplicate_root,
        reporter_chat_id=reporter_chat_id,
        reporter_lang=reporter_lang,
    )
    session.add(signal)
    await session.flush()

    await audit.record_transition(
        session,
        entity_type=EntityType.SIGNAL,
        entity_id=signal.id,
        from_status=None,
        to_status=SignalStatus.NEW,
        actor=actor,
        comment=None,
        meta={"duplicate_of": str(duplicate_root)} if duplicate_root else {},
    )

    parcel_status: ParcelStatus | None = None
    if match is not None:
        parcel = await get_parcel(session, match.parcel_id, for_update=True)
        if parcel.status is ParcelStatus.OK:
            await apply_transition(
                session,
                parcel,
                to=ParcelStatus.UNDER_CHECK,
                actor=SYSTEM_ACTOR,
                comment=code,
                meta={"auto": "signal", "signal_id": str(signal.id), "signal_code": code},
                notify=False,
            )
        parcel_status = parcel.status

    if reporter_chat_id is not None:
        await session.execute(
            insert(TelegramUser)
            .values(chat_id=reporter_chat_id, lang=reporter_lang, signals_count=1, last_signal_at=now)
            .on_conflict_do_update(
                index_elements=[TelegramUser.chat_id],
                set_={"signals_count": TelegramUser.signals_count + 1, "last_signal_at": now},
            )
        )

    await audit.emit_event(
        session,
        EventType.SIGNAL_CREATED,
        {
            "signal_id": str(signal.id),
            "tracking_code": code,
            "category": category.value,
            "lat": lat,
            "lon": lon,
            "parcel_id": str(match.parcel_id) if match else None,
            "parcel_status": parcel_status.value if parcel_status else None,
            "duplicate_of": str(duplicate_root) if duplicate_root else None,
        },
    )
    await session.flush()
    return signal


async def attach_photos(
    session: AsyncSession,
    storage: StorageProvider,
    signal_id: uuid.UUID,
    photos: Sequence[bytes],
    uploaded_by: str,
    source: PhotoSource = PhotoSource.CITIZEN,
) -> int:
    saved = len(
        await save_photos(
            session,
            storage,
            [PhotoSpec(PhotoOwnerType.SIGNAL, signal_id, data, source, uploaded_by) for data in photos],
        )
    )
    if saved:
        await audit.emit_event(
            session,
            EventType.PHOTO_ADDED,
            {"owner_type": "SIGNAL", "owner_id": str(signal_id), "count": saved},
        )
    return saved


async def summaries(
    session: AsyncSession, storage: StorageProvider, query: Select[tuple[Signal]]
) -> list[SignalSummary]:
    # Coordinates and the parcel's cadastral number come with the main query (fewer round trips).
    rows = (
        await session.execute(
            query.add_columns(
                func.ST_Y(Signal.location), func.ST_X(Signal.location), Parcel.cadastral_number
            ).outerjoin(Parcel, Parcel.id == Signal.parcel_id)
        )
    ).all()
    if not rows:
        return []
    signals = [row[0] for row in rows]
    ids = [s.id for s in signals]
    coords = {row[0].id: (row[1], row[2]) for row in rows}
    cadastral: dict[uuid.UUID, str] = {
        row[0].parcel_id: row[3] for row in rows if row[0].parcel_id and row[3]
    }
    roots = {s.duplicate_of or s.id for s in signals}
    dup_counts: dict[uuid.UUID | None, int] = dict(
        (
            await session.execute(
                select(Signal.duplicate_of, func.count(Signal.id))
                .where(Signal.duplicate_of.in_(roots))
                .group_by(Signal.duplicate_of)
            )
        )
        .tuples()
        .all()
    )
    photo_rows = (
        await session.execute(
            select(Photo.owner_id, Photo.thumb_path)
            .where(Photo.owner_type == PhotoOwnerType.SIGNAL, Photo.owner_id.in_(ids))
            .order_by(Photo.created_at, Photo.id)
        )
    ).all()
    first_thumb: dict[uuid.UUID, str] = {}
    photo_counts: dict[uuid.UUID, int] = {}
    for owner_id, thumb in photo_rows:
        first_thumb.setdefault(owner_id, thumb)
        photo_counts[owner_id] = photo_counts.get(owner_id, 0) + 1
    urls = await storage.signed_urls(list(first_thumb.values()))

    result = []
    for s in signals:
        lat, lon = coords[s.id]
        root = s.duplicate_of or s.id
        result.append(
            SignalSummary(
                id=str(s.id),
                tracking_code=s.tracking_code,
                category=s.category,
                status=s.status,
                description=s.description,
                address=s.address,
                lat=lat,
                lon=lon,
                parcel_id=str(s.parcel_id) if s.parcel_id else None,
                parcel_cadastral_number=cadastral.get(s.parcel_id) if s.parcel_id else None,
                duplicate_of=str(s.duplicate_of) if s.duplicate_of else None,
                reports_count=1 + int(dup_counts.get(root, 0)),
                thumb_url=urls.get(first_thumb[s.id]) if s.id in first_thumb else None,
                photos_count=photo_counts.get(s.id, 0),
                created_at=s.created_at,
            )
        )
    return result


async def list_signals(
    session: AsyncSession,
    storage: StorageProvider,
    *,
    statuses: list[SignalStatus],
    include_duplicates: bool,
    limit: int,
    offset: int,
) -> SignalList:
    query = select(Signal)
    if statuses:
        query = query.where(Signal.status.in_(statuses))
    if not include_duplicates:
        query = query.where(Signal.duplicate_of.is_(None))
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    # Open signals first, newest on top.
    ordered = query.order_by(Signal.status.in_(OPEN_STATUSES).desc(), Signal.created_at.desc())
    items = await summaries(session, storage, ordered.limit(limit).offset(offset))
    return SignalList(items=items, total=total)


async def get_signal(session: AsyncSession, signal_id: uuid.UUID, *, for_update: bool = False) -> Signal:
    query = select(Signal).where(Signal.id == signal_id)
    if for_update:
        query = query.with_for_update()
    signal = await session.scalar(query)
    if signal is None:
        raise NotFoundError("Signal not found", details={"signal_id": str(signal_id)})
    return signal


async def get_by_code(session: AsyncSession, code: str) -> Signal | None:
    return await session.scalar(select(Signal).where(Signal.tracking_code == code))


async def get_detail(session: AsyncSession, storage: StorageProvider, signal_id: uuid.UUID) -> SignalDetail:
    signal = await get_signal(session, signal_id)
    [summary] = await summaries(session, storage, select(Signal).where(Signal.id == signal_id))
    duplicates = await summaries(
        session, storage, select(Signal).where(Signal.duplicate_of == signal.id).order_by(Signal.created_at)
    )
    photos = await photos_for(session, storage, PhotoOwnerType.SIGNAL, [signal.id])
    return SignalDetail(
        **summary.model_dump(),
        reporter_lang=signal.reporter_lang,
        has_reporter=signal.reporter_chat_id is not None,
        parcel_distance_m=signal.parcel_distance_m,
        resolution_comment=signal.resolution_comment,
        allowed_transitions=allowed_transitions(EntityType.SIGNAL, signal.status),
        photos=photos.get(signal.id, []),
        duplicates=duplicates,
        history=await audit.history(session, EntityType.SIGNAL, signal.id),
    )


async def _set_status(
    session: AsyncSession, signal: Signal, to: SignalStatus, actor: str, comment: str, meta: dict[str, Any]
) -> None:
    ensure_transition(EntityType.SIGNAL, signal.status, to)
    previous = signal.status
    signal.status = to
    signal.updated_at = datetime.now(UTC)
    if to in (SignalStatus.CONFIRMED, SignalStatus.REJECTED):
        signal.resolution_comment = comment
    await audit.record_transition(
        session,
        entity_type=EntityType.SIGNAL,
        entity_id=signal.id,
        from_status=previous,
        to_status=to,
        actor=actor,
        comment=comment,
        meta=meta,
    )
    await audit.emit_event(
        session,
        EventType.SIGNAL_STATUS_CHANGED,
        {
            "signal_id": str(signal.id),
            "tracking_code": signal.tracking_code,
            "from": previous.value,
            "to": to.value,
            "parcel_id": str(signal.parcel_id) if signal.parcel_id else None,
        },
    )
    await notifier.signal_status_changed(session, signal, to, comment)


async def transition(
    session: AsyncSession, signal_id: uuid.UUID, request: SignalTransitionRequest, actor: str
) -> Signal:
    signal = await get_signal(session, signal_id, for_update=True)
    await _set_status(session, signal, request.to, actor, request.comment, {})

    # Duplicates follow their root, so every citizen who reported the spot is informed.
    if signal.duplicate_of is None:
        duplicates = await session.scalars(
            select(Signal)
            .where(Signal.duplicate_of == signal.id, Signal.status.in_(OPEN_STATUSES))
            .with_for_update()
        )
        for duplicate in duplicates:
            if can_transition(EntityType.SIGNAL, duplicate.status, request.to):
                await _set_status(
                    session,
                    duplicate,
                    request.to,
                    actor,
                    request.comment,
                    {"cascade_from": signal.tracking_code},
                )

    if signal.parcel_id is not None:
        parcel = await get_parcel(session, signal.parcel_id, for_update=True)
        if request.to is SignalStatus.CONFIRMED and can_transition(
            EntityType.PARCEL, parcel.status, ParcelStatus.VIOLATION
        ):
            await apply_transition(
                session,
                parcel,
                to=ParcelStatus.VIOLATION,
                actor=actor,
                comment=request.comment,
                violation_type=request.violation_type or SIGNAL_CATEGORY_TO_VIOLATION[signal.category],
                deadline_at=request.deadline_at,
                meta={"signal_id": str(signal.id), "signal_code": signal.tracking_code},
                notify=False,
            )
        elif request.to is SignalStatus.REJECTED and parcel.status is ParcelStatus.UNDER_CHECK:
            await session.flush()
            still_open = await session.scalar(
                select(func.count(Signal.id)).where(
                    Signal.parcel_id == parcel.id, Signal.status.in_(OPEN_STATUSES)
                )
            )
            if not still_open:
                await apply_transition(
                    session,
                    parcel,
                    to=ParcelStatus.OK,
                    actor=SYSTEM_ACTOR,
                    comment=signal.tracking_code,
                    meta={"auto": "signals_rejected", "signal_code": signal.tracking_code},
                    notify=False,
                )
    await session.flush()
    return signal


async def signals_for_chat(session: AsyncSession, chat_id: int, limit: int = 10) -> list[Signal]:
    return list(
        await session.scalars(
            select(Signal)
            .where(Signal.reporter_chat_id == chat_id)
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
    )
