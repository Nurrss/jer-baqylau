"""Idempotent demo seed and demo reset.

* ``seed_if_empty`` — used on container start: does nothing when parcels exist.
* ``reset`` — wipes domain data and re-seeds (``make demo-reset``). Telegram users,
  their subscriptions and language choices survive, because seeded entities have
  deterministic UUIDs.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml
from geoalchemy2 import Geography
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import Numeric, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import SEED_DIR
from app.core.logging import get_logger
from app.db.models import Application, Parcel, Photo, Signal, StatusTransition
from app.domain.enums import (
    ApplicationStatus,
    ApplicationType,
    EntityType,
    EventType,
    Lang,
    OwnerType,
    ParcelPurpose,
    ParcelStatus,
    PhotoOwnerType,
    PhotoSource,
    SignalCategory,
    SignalStatus,
    ViolationType,
)
from app.domain.tracking import format_signal_code
from app.providers.satellite import get_satellite_provider
from app.providers.storage import StorageProvider
from app.schemas.misc import DemoResetResponse
from app.seed.organizers import load_features
from app.services import audit, satellite
from app.services.outbox import after_commit
from app.services.photos import PhotoSpec, save_photos
from app.services.placeholders import placeholder_photo

log = get_logger(__name__)

NAMESPACE = uuid.UUID("6f1c2d4e-9a0b-4c3d-8e7f-1a2b3c4d5e6f")
INSPECTOR_ACTOR = "inspector:inspector@jer.kz"
SYSTEM_ACTOR = "system"
M_PER_DEG_LAT = 111_132.0

VIOLATION_COMMENTS: dict[ViolationType, str] = {
    ViolationType.UNUSED: "Участок не используется по назначению более года, признаков освоения нет.",
    ViolationType.DUMP: "На участке несанкционированная свалка бытовых и строительных отходов.",
    ViolationType.SELF_SEIZURE: "Выявлен самовольный захват: ограждение вынесено за границы участка.",
    ViolationType.MISUSE: "Участок используется не в соответствии с целевым назначением.",
}

# Tables wiped on reset. Events keep their id sequence so polling clients never go backwards.
RESET_TABLES = ("photos", "status_transitions", "ndvi_scans", "signals", "applications", "parcels")


def det_uuid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


def _read_yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((SEED_DIR / name).read_text(encoding="utf-8")) or {}


def parcel_features() -> list[dict[str, Any]]:
    source = os.getenv("SEED_PARCELS_SOURCE", "auto").lower()
    organizers_dir = SEED_DIR / "organizers"
    organizers = load_features(organizers_dir) if organizers_dir.is_dir() and source != "generated" else []
    generated: list[dict[str, Any]] = []
    if source in ("generated", "both") or (source == "auto" and not organizers):
        generated = json.loads((SEED_DIR / "parcels.geojson").read_text(encoding="utf-8"))["features"]
    return generated + organizers


@dataclass(slots=True)
class _Clock:
    now: datetime

    def ago(self, *, days: float = 0, hours: float = 0) -> datetime:
        return self.now - timedelta(days=days, hours=hours)


async def _transition(
    session: AsyncSession,
    entity_type: EntityType,
    entity_id: uuid.UUID,
    from_status: str | None,
    to_status: str,
    at: datetime,
    actor: str,
    comment: str | None,
    meta: dict[str, Any] | None = None,
) -> None:
    session.add(
        StatusTransition(
            entity_type=entity_type,
            entity_id=entity_id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            comment=comment,
            meta=meta or {},
            created_at=at,
        )
    )


def _parcel_path(status: ParcelStatus) -> list[ParcelStatus]:
    """Plausible status history ending in ``status`` (excluding the initial OK)."""
    return {
        ParcelStatus.OK: [],
        ParcelStatus.UNDER_CHECK: [ParcelStatus.UNDER_CHECK],
        ParcelStatus.VIOLATION: [ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION],
        ParcelStatus.IN_REMEDIATION: [ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION],
        ParcelStatus.RESOLVED: [
            ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION, ParcelStatus.RESOLVED,
        ],
        ParcelStatus.RETURNED_TO_STATE: [
            ParcelStatus.UNDER_CHECK, ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION,
            ParcelStatus.RETURNED_TO_STATE,
        ],
    }[status]  # fmt: skip


STEP_COMMENTS: dict[ParcelStatus, str] = {
    ParcelStatus.UNDER_CHECK: "Включён в план проверок по результатам мониторинга.",
    ParcelStatus.IN_REMEDIATION: "Собственнику выдано предписание, установлен срок устранения.",
    ParcelStatus.RESOLVED: "Повторный осмотр: нарушение устранено.",
    ParcelStatus.RETURNED_TO_STATE: "Предписание не исполнено. По решению суда участок возвращён в госсобственность.",
}


async def _seed_parcels(session: AsyncSession, clock: _Clock) -> dict[str, Parcel]:
    parcels: dict[str, Parcel] = {}
    for feature in parcel_features():
        props = feature["properties"]
        cadastral = props["cadastral_number"]
        if cadastral in parcels:
            log.warning("seed_duplicate_cadastral", cadastral=cadastral)
            continue
        status = ParcelStatus(props.get("seed_status") or ParcelStatus.OK)
        violation = ViolationType(props["seed_violation_type"]) if props.get("seed_violation_type") else None
        if status in (ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION) and violation is None:
            violation = ViolationType.MISUSE
        deadline_days = props.get("seed_deadline_days")
        geom = func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(feature["geometry"])), 4326))
        parcel = Parcel(
            id=det_uuid("parcel", cadastral),
            cadastral_number=cadastral,
            geometry=geom,
            centroid=func.ST_PointOnSurface(geom),
            area_ha=func.round(cast(func.ST_Area(cast(geom, Geography)) / 10_000, Numeric), 4),
            purpose=ParcelPurpose(props["purpose"]),
            owner_type=OwnerType(props["owner_type"]),
            address_ru=props["address_ru"],
            address_kk=props["address_kk"],
            district=props["district"],
            lease_until=datetime.fromisoformat(props["lease_until"]).date()
            if props.get("lease_until")
            else None,
            status=status,
            violation_type=violation if status is not ParcelStatus.OK else None,
            deadline_at=(
                (clock.now + timedelta(days=deadline_days)).replace(
                    hour=18, minute=0, second=0, microsecond=0
                )
                if deadline_days is not None
                else None
            ),
            inspector_id=INSPECTOR_ACTOR if status is not ParcelStatus.OK else None,
            source=props.get("source", "seed"),
        )
        session.add(parcel)
        parcels[cadastral] = parcel

        # History, spaced out in the past (violation found ≈ deadline − 30 days).
        path = _parcel_path(status)
        previous = ParcelStatus.OK
        start_days = 45 + (hash_int(cadastral) % 20)
        for i, step in enumerate(path):
            at = clock.ago(days=start_days - i * 9)
            comment = (
                VIOLATION_COMMENTS.get(violation or ViolationType.MISUSE)
                if step is ParcelStatus.VIOLATION
                else (STEP_COMMENTS.get(step))
            )
            await _transition(
                session,
                EntityType.PARCEL,
                parcel.id,
                previous.value,
                step.value,
                at,
                INSPECTOR_ACTOR,
                comment,
                {"violation_type": violation.value} if violation and step is ParcelStatus.VIOLATION else None,
            )
            previous = step
    await session.flush()
    return parcels


def hash_int(value: str) -> int:
    return int(uuid.uuid5(NAMESPACE, value).hex[:8], 16)


async def _seed_applications(session: AsyncSession, parcels: dict[str, Parcel], clock: _Clock) -> int:
    items = _read_yaml("applications.yaml")["applications"]
    for item in items:
        history = item["history"]
        last = history[-1]
        application = Application(
            id=det_uuid("application", item["number"]),
            tracking_number=item["number"],
            applicant_name=item["applicant"],
            type=ApplicationType(item["type"]),
            status=ApplicationStatus(last["status"]),
            status_comment_ru=last["ru"],
            status_comment_kk=last["kk"],
            inspection_date=None,
            parcel_id=parcels[item["parcel"]].id if item.get("parcel") in parcels else None,
            submitted_at=clock.ago(days=item["submitted_days_ago"]),
            updated_at=clock.ago(days=last["days_ago"]),
        )
        previous: str | None = None
        for step in history:
            if "inspection_in_days" in step:
                application.inspection_date = (clock.now + timedelta(days=step["inspection_in_days"])).date()
            await _transition(
                session,
                EntityType.APPLICATION,
                application.id,
                previous,
                step["status"],
                clock.ago(days=step["days_ago"]),
                INSPECTOR_ACTOR if previous else "citizen",
                step["ru"],
                {"comment_kk": step["kk"]},
            )
            previous = step["status"]
        session.add(application)
    await session.flush()
    return len(items)


async def _seed_signals(
    session: AsyncSession, storage: StorageProvider, parcels: dict[str, Parcel], clock: _Clock
) -> int:
    items = sorted(_read_yaml("signals.yaml")["signals"], key=lambda s: -s["hours_ago"])
    ids: dict[str, uuid.UUID] = {}
    specs: list[PhotoSpec] = []
    created_by_signal: dict[uuid.UUID, datetime] = {}
    centroids = {
        c: (lon, lat)
        for c, lon, lat in await session.execute(
            select(Parcel.cadastral_number, func.ST_X(Parcel.centroid), func.ST_Y(Parcel.centroid))
        )
    }
    for seq, item in enumerate(items, start=1):
        if item.get("parcel") and item["parcel"] not in parcels:
            log.warning("seed_signal_parcel_missing", key=item["key"])
            continue
        if item.get("location"):
            lat, lon = item["location"]
            parcel_id = None
        else:
            lon0, lat0 = centroids[item["parcel"]]
            dx, dy = item.get("offset_m", [0, 0])
            lat = lat0 + dy / M_PER_DEG_LAT
            lon = lon0 + dx / (M_PER_DEG_LAT * math.cos(math.radians(lat0)))
            parcel_id = parcels[item["parcel"]].id
        created = clock.ago(hours=item["hours_ago"])
        status = SignalStatus(item["status"])
        signal = Signal(
            id=det_uuid("signal", item["key"]),
            tracking_code=format_signal_code(clock.now.year, seq),
            location=from_shape(Point(lon, lat), srid=4326),
            category=SignalCategory(item["category"]),
            description=item.get("description"),
            address=None,
            status=status,
            parcel_id=parcel_id,
            parcel_distance_m=0.0 if parcel_id else None,
            duplicate_of=ids.get(item.get("duplicate_of", "")),
            reporter_chat_id=None,
            reporter_lang=Lang(item.get("lang", "ru")),
            resolution_comment=item.get("comment")
            if status in (SignalStatus.CONFIRMED, SignalStatus.REJECTED)
            else None,
            created_at=created,
            updated_at=created,
        )
        session.add(signal)
        ids[item["key"]] = signal.id
        await _transition(
            session, EntityType.SIGNAL, signal.id, None, SignalStatus.NEW.value, created, "citizen", None
        )
        if status is not SignalStatus.NEW:
            reacted = created + timedelta(hours=3 + hash_int(item["key"]) % 20)
            await _transition(
                session,
                EntityType.SIGNAL,
                signal.id,
                SignalStatus.NEW.value,
                status.value,
                reacted,
                INSPECTOR_ACTOR,
                item.get("comment"),
            )
        await session.flush()
        created_by_signal[signal.id] = created
        specs += [
            PhotoSpec(
                PhotoOwnerType.SIGNAL,
                signal.id,
                placeholder_photo(f"{item['key']}:{n}", signal.category),
                PhotoSource.CITIZEN,
                "citizen",
            )
            for n in range(int(item.get("photos", 0)))
        ]
    for photo in await save_photos(session, storage, specs):
        photo.created_at = created_by_signal[photo.owner_id]
    await session.execute(text("SELECT setval('signal_tracking_seq', :v, true)"), {"v": max(len(items), 1)})
    return len(ids)


async def _seed_inspector_photos(
    session: AsyncSession, storage: StorageProvider, parcels: dict[str, Parcel]
) -> None:
    category = {
        ViolationType.DUMP: SignalCategory.DUMP,
        ViolationType.UNUSED: SignalCategory.ABANDONED,
        ViolationType.SELF_SEIZURE: SignalCategory.SELF_SEIZURE,
        ViolationType.MISUSE: SignalCategory.OTHER,
    }
    specs = [
        PhotoSpec(
            PhotoOwnerType.PARCEL,
            parcel.id,
            placeholder_photo(f"inspector:{parcel.cadastral_number}", category[parcel.violation_type]),
            PhotoSource.INSPECTOR,
            INSPECTOR_ACTOR,
        )
        for parcel in parcels.values()
        if parcel.status in (ParcelStatus.VIOLATION, ParcelStatus.IN_REMEDIATION) and parcel.violation_type
    ]
    await save_photos(session, storage, specs)


async def seed(session: AsyncSession, storage: StorageProvider) -> DemoResetResponse:
    clock = _Clock(now=datetime.now(UTC))
    parcels = await _seed_parcels(session, clock)
    applications = await _seed_applications(session, parcels, clock)
    signals = await _seed_signals(session, storage, parcels, clock)
    await _seed_inspector_photos(session, storage, parcels)
    provider = get_satellite_provider()
    if provider.is_demo:
        await satellite.run_scan(session, provider)
    else:
        # A real Sentinel-2 scan takes tens of seconds: run it after the reset is committed.
        from app.workers.scheduler import start_scan_in_background

        async def scan_later() -> None:
            start_scan_in_background()

        after_commit(session, scan_later)
    log.info("seed_completed", parcels=len(parcels), applications=applications, signals=signals)
    return DemoResetResponse(parcels=len(parcels), applications=applications, signals=signals)


async def seed_if_empty(session: AsyncSession, storage: StorageProvider) -> DemoResetResponse | None:
    # Serialize concurrent starts (several replicas / workers) on an advisory lock.
    await session.execute(text("SELECT pg_advisory_xact_lock(724001)"))
    if await session.scalar(select(func.count(Parcel.id))):
        log.info("seed_skipped_not_empty")
        return None
    return await seed(session, storage)


async def reset(session: AsyncSession, storage: StorageProvider) -> DemoResetResponse:
    await session.execute(text("SELECT pg_advisory_xact_lock(724001)"))
    paths = [p for row in await session.execute(select(Photo.storage_path, Photo.thumb_path)) for p in row]
    await session.execute(text(f"TRUNCATE {', '.join(RESET_TABLES)} RESTART IDENTITY CASCADE"))
    await session.execute(text("DELETE FROM events"))
    result = await seed(session, storage)
    await audit.emit_event(session, EventType.DEMO_RESET, result.model_dump())
    if paths:
        # New photos get new paths; drop the old files only once the reset is committed.
        after_commit(session, lambda: storage.delete(paths))
    return result
