"""Parcel queries and lifecycle."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.db.models import Parcel, Signal
from app.domain.enums import (
    EntityType,
    EventType,
    OwnerType,
    ParcelPurpose,
    ParcelStatus,
    PhotoOwnerType,
    SignalStatus,
    ViolationType,
)
from app.domain.state_machine import ACTIVE_VIOLATION_STATUSES, allowed_transitions, ensure_transition
from app.providers.storage import StorageProvider
from app.schemas.common import LngLat
from app.schemas.parcels import (
    ParcelDetail,
    ParcelFeature,
    ParcelFeatureCollection,
    ParcelProperties,
    ParcelSearchResult,
    ParcelTransitionRequest,
    ParcelUpdateRequest,
)
from app.services import audit, notifier
from app.services.photos import photos_for

DEFAULT_DEADLINE_DAYS = 30
GEOJSON_PRECISION = 6


@dataclass(slots=True)
class ParcelFilters:
    bbox: tuple[float, float, float, float] | None = None
    statuses: list[ParcelStatus] = field(default_factory=list)
    violation_types: list[ViolationType] = field(default_factory=list)
    purposes: list[ParcelPurpose] = field(default_factory=list)
    overdue: bool | None = None


def overdue_clause(now: datetime) -> ColumnElement[bool]:
    return and_(
        Parcel.deadline_at.is_not(None),
        Parcel.deadline_at < now,
        Parcel.status.in_(ACTIVE_VIOLATION_STATUSES),
    )


def _open_signals_count() -> Any:
    return (
        select(func.count(Signal.id))
        .where(Signal.parcel_id == Parcel.id, Signal.status.in_([SignalStatus.NEW, SignalStatus.IN_REVIEW]))
        .correlate(Parcel)
        .scalar_subquery()
    )


def _base_query(now: datetime) -> Select[Any]:
    return select(
        Parcel,
        func.ST_AsGeoJSON(Parcel.geometry, GEOJSON_PRECISION).label("geojson"),
        case((overdue_clause(now), True), else_=False).label("is_overdue"),
        _open_signals_count().label("open_signals"),
    )


def _properties(parcel: Parcel, is_overdue: bool, open_signals: int) -> dict[str, Any]:
    return {
        "id": str(parcel.id),
        "cadastral_number": parcel.cadastral_number,
        "status": parcel.status,
        "violation_type": parcel.violation_type,
        "purpose": parcel.purpose,
        "owner_type": parcel.owner_type,
        "area_ha": float(parcel.area_ha),
        "address_ru": parcel.address_ru,
        "address_kk": parcel.address_kk,
        "district": parcel.district,
        "deadline_at": parcel.deadline_at,
        "is_overdue": bool(is_overdue),
        "ndvi": parcel.ndvi,
        "ndvi_flagged": parcel.ndvi_flagged,
        "open_signals_count": int(open_signals or 0),
    }


async def list_geojson(session: AsyncSession, filters: ParcelFilters) -> ParcelFeatureCollection:
    now = datetime.now(UTC)
    query = _base_query(now)
    if filters.bbox:
        query = query.where(func.ST_Intersects(Parcel.geometry, func.ST_MakeEnvelope(*filters.bbox, 4326)))
    if filters.statuses:
        query = query.where(Parcel.status.in_(filters.statuses))
    if filters.violation_types:
        query = query.where(Parcel.violation_type.in_(filters.violation_types))
    if filters.purposes:
        query = query.where(Parcel.purpose.in_(filters.purposes))
    if filters.overdue is True:
        query = query.where(overdue_clause(now))
    elif filters.overdue is False:
        query = query.where(~overdue_clause(now))
    rows = (await session.execute(query.order_by(Parcel.cadastral_number))).all()
    features = [
        ParcelFeature(
            id=str(parcel.id),
            geometry=json.loads(geojson),
            properties=ParcelProperties(**_properties(parcel, is_overdue, open_signals)),
        )
        for parcel, geojson, is_overdue, open_signals in rows
    ]
    return ParcelFeatureCollection(features=features)


async def search(session: AsyncSession, q: str, limit: int = 10) -> list[ParcelSearchResult]:
    term = q.strip()
    if len(term) < 2:
        return []
    like = f"%{term}%"
    query = (
        select(
            Parcel,
            func.ST_X(Parcel.centroid),
            func.ST_Y(Parcel.centroid),
            func.ST_XMin(Parcel.geometry),
            func.ST_YMin(Parcel.geometry),
            func.ST_XMax(Parcel.geometry),
            func.ST_YMax(Parcel.geometry),
        )
        .where(
            or_(
                Parcel.cadastral_number.ilike(like),
                Parcel.address_ru.ilike(like),
                Parcel.address_kk.ilike(like),
            )
        )
        .order_by(
            case(
                (Parcel.cadastral_number == term, 0), (Parcel.cadastral_number.ilike(f"{term}%"), 1), else_=2
            ),
            Parcel.cadastral_number,
        )
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    return [
        ParcelSearchResult(
            id=str(p.id),
            cadastral_number=p.cadastral_number,
            address_ru=p.address_ru,
            address_kk=p.address_kk,
            status=p.status,
            centroid=LngLat(lon=x, lat=y),
            bbox=[x0, y0, x1, y1],
        )
        for p, x, y, x0, y0, x1, y1 in rows
    ]


async def get_parcel(session: AsyncSession, parcel_id: uuid.UUID, *, for_update: bool = False) -> Parcel:
    query = select(Parcel).where(Parcel.id == parcel_id)
    if for_update:
        query = query.with_for_update()
    parcel = await session.scalar(query)
    if parcel is None:
        raise NotFoundError("Parcel not found", details={"parcel_id": str(parcel_id)})
    return parcel


async def get_detail(session: AsyncSession, storage: StorageProvider, parcel_id: uuid.UUID) -> ParcelDetail:
    from app.services.signals import summaries

    now = datetime.now(UTC)
    row = (
        await session.execute(
            _base_query(now)
            .add_columns(
                func.ST_X(Parcel.centroid),
                func.ST_Y(Parcel.centroid),
                func.ST_XMin(Parcel.geometry),
                func.ST_YMin(Parcel.geometry),
                func.ST_XMax(Parcel.geometry),
                func.ST_YMax(Parcel.geometry),
            )
            .where(Parcel.id == parcel_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Parcel not found", details={"parcel_id": str(parcel_id)})
    parcel, geojson, is_overdue, open_signals, cx, cy, x0, y0, x1, y1 = row

    photos = await photos_for(session, storage, PhotoOwnerType.PARCEL, [parcel.id])
    signal_items = await summaries(
        session,
        storage,
        select(Signal).where(Signal.parcel_id == parcel.id).order_by(Signal.created_at.desc()),
    )
    return ParcelDetail(
        **_properties(parcel, is_overdue, open_signals),
        geometry=json.loads(geojson),
        centroid=LngLat(lon=cx, lat=cy),
        bbox=[x0, y0, x1, y1],
        lease_until=parcel.lease_until,
        inspector_id=parcel.inspector_id,
        ndvi_scanned_at=parcel.ndvi_scanned_at,
        ndvi_observed_at=parcel.ndvi_observed_at,
        ndvi_scene_id=parcel.ndvi_scene_id,
        updated_at=parcel.updated_at,
        allowed_transitions=allowed_transitions(EntityType.PARCEL, parcel.status),
        photos=photos.get(parcel.id, []),
        signals=signal_items,
        history=await audit.history(session, EntityType.PARCEL, parcel.id),
    )


async def apply_transition(
    session: AsyncSession,
    parcel: Parcel,
    *,
    to: ParcelStatus,
    actor: str,
    comment: str,
    violation_type: ViolationType | None = None,
    deadline_at: datetime | None = None,
    meta: dict[str, Any] | None = None,
    notify: bool = True,
) -> Parcel:
    """Validate and apply a status change, with audit, event and citizen notifications.

    ``notify=False`` when the change is a side effect of a signal transition — the
    citizen already gets a message about their signal.
    """
    ensure_transition(EntityType.PARCEL, parcel.status, to)
    previous = parcel.status
    now = datetime.now(UTC)
    if deadline_at is not None and deadline_at <= now and to in ACTIVE_VIOLATION_STATUSES:
        raise ValidationFailedError("deadline_at must be in the future", code="DEADLINE_IN_PAST")

    if to is ParcelStatus.RESOLVED:
        # No "fixed" on the inspector's word alone: fresh evidence must exist (see services/evidence.py).
        from app.services.evidence import resolution_evidence

        evidence = await resolution_evidence(session, parcel)
        if not evidence.sufficient:
            raise ValidationFailedError(
                "Evidence is required to close the violation",
                code="EVIDENCE_REQUIRED",
                details=evidence.model_dump(mode="json"),
            )

    if to is ParcelStatus.VIOLATION:
        resolved_type = violation_type or parcel.violation_type
        if resolved_type is None:
            raise ValidationFailedError(
                "violation_type is required to register a violation", code="VIOLATION_TYPE_REQUIRED"
            )
        parcel.violation_type = resolved_type
        parcel.deadline_at = deadline_at or (now + timedelta(days=DEFAULT_DEADLINE_DAYS))
    elif to is ParcelStatus.IN_REMEDIATION:
        if deadline_at is not None:
            parcel.deadline_at = deadline_at
        if violation_type is not None:
            parcel.violation_type = violation_type
    elif to is ParcelStatus.OK:
        parcel.violation_type = None
        parcel.deadline_at = None
    elif to is ParcelStatus.RETURNED_TO_STATE:
        parcel.owner_type = OwnerType.STATE
        parcel.lease_until = None

    parcel.status = to
    parcel.updated_at = now
    await audit.record_transition(
        session,
        entity_type=EntityType.PARCEL,
        entity_id=parcel.id,
        from_status=previous,
        to_status=to,
        actor=actor,
        comment=comment,
        meta={
            **(meta or {}),
            **({"violation_type": parcel.violation_type.value} if parcel.violation_type else {}),
            **({"deadline_at": parcel.deadline_at.isoformat()} if parcel.deadline_at else {}),
        },
    )
    await audit.emit_event(
        session,
        EventType.PARCEL_STATUS_CHANGED,
        {
            "parcel_id": str(parcel.id),
            "cadastral_number": parcel.cadastral_number,
            "from": previous.value,
            "to": to.value,
            "actor": actor,
        },
    )
    await session.flush()
    if notify:
        await notifier.parcel_status_changed(session, parcel)
    return parcel


async def transition(
    session: AsyncSession, parcel_id: uuid.UUID, request: ParcelTransitionRequest, actor: str
) -> Parcel:
    parcel = await get_parcel(session, parcel_id, for_update=True)
    return await apply_transition(
        session,
        parcel,
        to=request.to,
        actor=actor,
        comment=request.comment,
        violation_type=request.violation_type,
        deadline_at=request.deadline_at,
    )


async def update(
    session: AsyncSession, parcel_id: uuid.UUID, request: ParcelUpdateRequest, actor: str
) -> Parcel:
    parcel = await get_parcel(session, parcel_id, for_update=True)
    changes: dict[str, Any] = {}
    if request.clear_deadline:
        parcel.deadline_at = None
        changes["deadline_at"] = None
    elif request.deadline_at is not None:
        parcel.deadline_at = request.deadline_at
        changes["deadline_at"] = request.deadline_at.isoformat()
    if request.inspector_id is not None:
        parcel.inspector_id = request.inspector_id or None
        changes["inspector_id"] = parcel.inspector_id
    if changes:
        parcel.updated_at = datetime.now(UTC)
        await audit.emit_event(
            session,
            EventType.PARCEL_UPDATED,
            {
                "parcel_id": str(parcel.id),
                "cadastral_number": parcel.cadastral_number,
                "changes": changes,
                "actor": actor,
            },
        )
        await session.flush()
    return parcel
