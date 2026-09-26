"""Remote inspections: the owner photographs the parcel on request; anti-fraud checks the report.

The owner opens a one-time link, the page takes photos **only from the live camera** (no gallery
upload) together with the device GPS position. The server then checks, without any trust in the
owner:

* ``LOCATION_ON_PARCEL`` — the device is on the parcel (within max(30 m, GPS accuracy));
* ``GPS_ACCURACY``       — the position is precise enough to be meaningful;
* ``PHOTOS_FRESH``       — photos were taken now, after the request was issued;
* ``PHOTOS_UNIQUE``      — none of the photos was seen before (perceptual hash, survives re-compression);
* ``EXIF_GPS``           — if a photo carries its own GPS, it matches the device position;
* ``SATELLITE``          — the declared use agrees with the latest Sentinel-2 NDVI.

Any ``fail`` → verdict FAIL, any ``warn`` → SUSPICIOUS, otherwise PASS. The inspector makes the final
decision (ACCEPTED / REJECTED); every step is written to the hash-chained audit log.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from geoalchemy2 import Geography
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.db.models import InspectionRequest, NdviScan, Parcel, Photo
from app.domain.enums import (
    DeclaredUse,
    EntityType,
    EventType,
    InspectionReason,
    InspectionStatus,
    InspectionVerdict,
    ParcelPurpose,
    PhotoOwnerType,
    PhotoSource,
)
from app.providers.satellite import UNUSED_NDVI_THRESHOLD
from app.providers.storage import StorageProvider
from app.services import audit
from app.services.photos import PhotoSpec, hamming, save_photos

LOCATION_TOLERANCE_M = 30
ACCURACY_OK_M = 50
ACCURACY_MAX_M = 150
FRESH_MAX_AGE = timedelta(minutes=20)
CLOCK_SKEW = timedelta(minutes=2)
DUPLICATE_HAMMING = 6
EXIF_MAX_DISTANCE_M = 200
SATELLITE_MAX_AGE = timedelta(days=60)
GROWING_MONTHS = range(4, 11)
MAX_PHOTOS = 5
DEFAULT_DUE_HOURS = 48
MOCK_PROVIDER = "mock-sentinel-2"

CheckStatus = Literal["pass", "warn", "fail", "skip"]


@dataclass(frozen=True, slots=True)
class Check:
    code: str
    status: CheckStatus
    params: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "status": self.status, "params": self.params}


def verdict_of(checks: Sequence[Check]) -> InspectionVerdict:
    statuses = {c.status for c in checks}
    if "fail" in statuses:
        return InspectionVerdict.FAIL
    if "warn" in statuses:
        return InspectionVerdict.SUSPICIOUS
    return InspectionVerdict.PASS


def public_link(request: InspectionRequest) -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/inspect/{request.token}"


async def _audit(
    session: AsyncSession,
    request: InspectionRequest,
    previous: InspectionStatus | None,
    actor: str,
    comment: str | None,
    meta: dict[str, Any] | None = None,
) -> None:
    await audit.record_transition(
        session,
        entity_type=EntityType.INSPECTION,
        entity_id=request.id,
        from_status=previous,
        to_status=request.status,
        actor=actor,
        comment=comment,
        meta={"code": request.code, "parcel_id": str(request.parcel_id), **(meta or {})},
    )


async def create_request(
    session: AsyncSession,
    parcel_id: uuid.UUID,
    *,
    reason: InspectionReason,
    actor: str,
    due_hours: int = DEFAULT_DUE_HOURS,
    note: str | None = None,
) -> InspectionRequest:
    parcel = await session.get(Parcel, parcel_id)
    if parcel is None:
        raise NotFoundError("Parcel not found", details={"parcel_id": str(parcel_id)})
    open_request = await session.scalar(
        select(InspectionRequest.code).where(
            InspectionRequest.parcel_id == parcel_id,
            or_(
                and_(
                    InspectionRequest.status == InspectionStatus.REQUESTED,
                    InspectionRequest.due_at > datetime.now(UTC),
                ),
                # A submitted report must be reviewed before the owner is asked again.
                InspectionRequest.status == InspectionStatus.SUBMITTED,
            ),
        )
    )
    if open_request:
        raise ConflictError(
            "An inspection request for this parcel is already open",
            code="INSPECTION_ALREADY_OPEN",
            details={"code": open_request},
        )
    now = datetime.now(UTC)
    seq = int(await session.scalar(select(func.nextval("inspection_code_seq"))) or 0)
    request = InspectionRequest(
        id=uuid.uuid4(),
        code=f"INS-{now:%Y}-{seq:04d}",
        token=secrets.token_urlsafe(24),
        parcel_id=parcel_id,
        reason=reason,
        status=InspectionStatus.REQUESTED,
        note=(note or "").strip()[:500] or None,
        requested_by=actor,
        due_at=now + timedelta(hours=max(1, min(due_hours, 24 * 14))),
        created_at=now,
        checks=[],
    )
    session.add(request)
    await session.flush()
    await _audit(session, request, None, actor, request.note, {"reason": reason.value})
    await audit.emit_event(
        session,
        EventType.INSPECTION_REQUESTED,
        {
            "inspection_id": str(request.id),
            "code": request.code,
            "parcel_id": str(parcel_id),
            "reason": reason.value,
        },
    )
    return request


async def expire_if_due(session: AsyncSession, request: InspectionRequest) -> None:
    if request.status is InspectionStatus.REQUESTED and request.due_at <= datetime.now(UTC):
        request.status = InspectionStatus.EXPIRED
        await _audit(session, request, InspectionStatus.REQUESTED, "system", "deadline passed")


async def get_by_token(session: AsyncSession, token: str) -> InspectionRequest:
    request = await session.scalar(select(InspectionRequest).where(InspectionRequest.token == token))
    if request is None:
        raise NotFoundError("Inspection link is invalid", code="INSPECTION_NOT_FOUND")
    await expire_if_due(session, request)
    return request


async def get_request(session: AsyncSession, request_id: uuid.UUID) -> InspectionRequest:
    request = await session.get(InspectionRequest, request_id)
    if request is None:
        raise NotFoundError("Inspection request not found", code="INSPECTION_NOT_FOUND")
    await expire_if_due(session, request)
    return request


# ── Anti-fraud ──────────────────────────────────────────────────────────────


async def _check_location(
    session: AsyncSession, parcel: Parcel, lat: float, lon: float, accuracy: float
) -> Check:
    point = cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)
    distance = float(
        await session.scalar(
            select(func.ST_Distance(cast(Parcel.geometry, Geography), point)).where(Parcel.id == parcel.id)
        )
        or 0.0
    )
    tolerance = max(LOCATION_TOLERANCE_M, min(accuracy, ACCURACY_MAX_M))
    return Check(
        "LOCATION_ON_PARCEL",
        "pass" if distance <= tolerance else "fail",
        {"distance_m": round(distance), "tolerance_m": round(tolerance)},
    )


def _check_accuracy(accuracy: float) -> Check:
    status: CheckStatus = (
        "pass" if accuracy <= ACCURACY_OK_M else "warn" if accuracy <= ACCURACY_MAX_M else "fail"
    )
    return Check("GPS_ACCURACY", status, {"accuracy_m": round(accuracy)})


def _check_fresh(request: InspectionRequest, captured: Sequence[datetime], received: datetime) -> Check:
    stale = [c for c in captured if c < request.created_at - CLOCK_SKEW or c > received + CLOCK_SKEW]
    oldest_age = max((received - c for c in captured), default=timedelta(0))
    ok = not stale and oldest_age <= FRESH_MAX_AGE
    return Check(
        "PHOTOS_FRESH",
        "pass" if ok else "fail",
        {
            "max_age_min": round(oldest_age.total_seconds() / 60),
            "limit_min": int(FRESH_MAX_AGE.total_seconds() // 60),
        },
    )


async def _check_unique(session: AsyncSession, new_photos: Sequence[Photo]) -> Check:
    new_ids = {p.id for p in new_photos}
    known = [
        (pid, ph)
        for pid, ph in (
            await session.execute(select(Photo.id, Photo.phash).where(Photo.phash.is_not(None)))
        ).all()
        if pid not in new_ids
    ]
    duplicates = 0
    for photo in new_photos:
        if photo.phash and any(hamming(photo.phash, other) <= DUPLICATE_HAMMING for _, other in known):
            duplicates += 1
    # The same shot sent twice within one report is suspicious but not proof of fraud.
    hashes = [p.phash for p in new_photos if p.phash]
    repeats = sum(
        1 for i, a in enumerate(hashes) for b in hashes[i + 1 :] if hamming(a, b) <= DUPLICATE_HAMMING
    )
    status: CheckStatus = "fail" if duplicates else "warn" if repeats else "pass"
    return Check("PHOTOS_UNIQUE", status, {"duplicates": duplicates, "repeats": repeats})


async def _check_exif(session: AsyncSession, new_photos: Sequence[Photo], lat: float, lon: float) -> Check:
    with_gps = [p for p in new_photos if p.location is not None]
    if not with_gps:
        return Check("EXIF_GPS", "skip", {})
    device = cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)
    far = await session.scalar(
        select(func.max(func.ST_Distance(cast(Photo.location, Geography), device))).where(
            Photo.id.in_([p.id for p in with_gps])
        )
    )
    distance = round(float(far or 0))
    return Check("EXIF_GPS", "pass" if distance <= EXIF_MAX_DISTANCE_M else "fail", {"distance_m": distance})


async def _check_satellite(
    session: AsyncSession, parcel: Parcel, declared: DeclaredUse, now: datetime
) -> Check:
    if parcel.purpose not in (ParcelPurpose.AGRICULTURE, ParcelPurpose.LPH):
        return Check("SATELLITE", "skip", {})
    if declared is DeclaredUse.FALLOW:
        return Check("SATELLITE", "warn", {"reason": "owner_admits_non_use"})
    scan = (
        await session.execute(
            select(NdviScan.ndvi, NdviScan.observed_at)
            .where(
                NdviScan.parcel_id == parcel.id,
                NdviScan.provider != MOCK_PROVIDER,
                NdviScan.observed_at.is_not(None),
            )
            .order_by(NdviScan.observed_at.desc())
            .limit(1)
        )
    ).first()
    if scan is None or scan[1] is None or now - scan[1] > SATELLITE_MAX_AGE:
        return Check("SATELLITE", "skip", {})
    ndvi, observed = float(scan[0]), scan[1]
    if (
        declared is DeclaredUse.CULTIVATED
        and observed.month in GROWING_MONTHS
        and ndvi < UNUSED_NDVI_THRESHOLD
    ):
        return Check("SATELLITE", "warn", {"ndvi": round(ndvi, 2), "date": observed.date().isoformat()})
    return Check("SATELLITE", "pass", {"ndvi": round(ndvi, 2), "date": observed.date().isoformat()})


async def submit(
    session: AsyncSession,
    storage: StorageProvider,
    token: str,
    *,
    files: Sequence[bytes],
    captured_at: Sequence[datetime],
    lat: float,
    lon: float,
    accuracy: float,
    declared_use: DeclaredUse,
    comment: str | None,
) -> InspectionRequest:
    request = await get_by_token(session, token)
    if request.status is not InspectionStatus.REQUESTED:
        raise ConflictError("This inspection link has already been used or expired", code="INSPECTION_CLOSED")
    if not 1 <= len(files) <= MAX_PHOTOS:
        raise ValidationFailedError(f"Send 1–{MAX_PHOTOS} photos", code="INSPECTION_PHOTOS")
    if len(captured_at) != len(files):
        raise ValidationFailedError("captured_at is required for every photo")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or accuracy <= 0:
        raise ValidationFailedError("Invalid device position")

    parcel = await session.get(Parcel, request.parcel_id)
    assert parcel is not None
    received = datetime.now(UTC)
    photos = await save_photos(
        session,
        storage,
        [
            PhotoSpec(PhotoOwnerType.INSPECTION, request.id, data, PhotoSource.OWNER, f"owner:{request.code}")
            for data in files
        ],
    )
    for photo, taken in zip(photos, captured_at, strict=True):
        photo.taken_at = taken
    await session.flush()

    checks = [
        await _check_location(session, parcel, lat, lon, accuracy),
        _check_accuracy(accuracy),
        _check_fresh(request, captured_at, received),
        await _check_unique(session, photos),
        await _check_exif(session, photos, lat, lon),
        await _check_satellite(session, parcel, declared_use, received),
    ]
    request.status = InspectionStatus.SUBMITTED
    request.submitted_at = received
    request.declared_use = declared_use
    request.owner_comment = (comment or "").strip()[:1000] or None
    request.device_location = from_shape(Point(lon, lat), srid=4326)
    request.accuracy_m = accuracy
    request.checks = [c.as_dict() for c in checks]
    request.verdict = verdict_of(checks)
    await _audit(
        session,
        request,
        InspectionStatus.REQUESTED,
        f"owner:{request.code}",
        request.owner_comment,
        {"verdict": request.verdict.value, "photos": [p.sha256 for p in photos]},
    )
    await audit.emit_event(
        session,
        EventType.INSPECTION_SUBMITTED,
        {
            "inspection_id": str(request.id),
            "code": request.code,
            "parcel_id": str(request.parcel_id),
            "verdict": request.verdict.value,
        },
    )
    await session.flush()
    return request


async def review(
    session: AsyncSession, request_id: uuid.UUID, *, decision: InspectionStatus, comment: str, actor: str
) -> InspectionRequest:
    if decision not in (InspectionStatus.ACCEPTED, InspectionStatus.REJECTED):
        raise ValidationFailedError("decision must be ACCEPTED or REJECTED")
    request = await get_request(session, request_id)
    if request.status is not InspectionStatus.SUBMITTED:
        raise ConflictError("Only a submitted report can be reviewed", code="INSPECTION_NOT_SUBMITTED")
    if decision is InspectionStatus.ACCEPTED and request.verdict is InspectionVerdict.FAIL:
        # A report that failed anti-fraud cannot be used as evidence.
        raise ConflictError(
            "A report that failed the anti-fraud checks cannot be accepted", code="INSPECTION_FAILED"
        )
    request.status = decision
    request.reviewed_by = actor
    request.review_comment = comment.strip()
    request.reviewed_at = datetime.now(UTC)
    await _audit(session, request, InspectionStatus.SUBMITTED, actor, request.review_comment)
    await audit.emit_event(
        session,
        EventType.INSPECTION_REVIEWED,
        {
            "inspection_id": str(request.id),
            "code": request.code,
            "parcel_id": str(request.parcel_id),
            "status": decision.value,
        },
    )
    await session.flush()
    return request
