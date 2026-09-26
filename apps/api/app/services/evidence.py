"""Evidence required to close a violation as RESOLVED.

An inspector cannot mark a violation as fixed on their word alone. At least one of these must
exist *after* the precept was issued (the last transition to IN_REMEDIATION):

* an inspector photo whose GPS position is on the parcel (≤ 50 m from its boundary);
* an owner photo report (remote inspection) that passed the anti-fraud checks and was accepted;
* for "unused land": a real (non-demo) satellite scene showing vegetation (NDVI ≥ 0.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InspectionRequest, NdviScan, Parcel, Photo, StatusTransition
from app.domain.enums import (
    EntityType,
    InspectionStatus,
    ParcelStatus,
    PhotoOwnerType,
    PhotoSource,
    ViolationType,
)
from app.schemas.common import ApiModel

EVIDENCE_RADIUS_M = 50
SATELLITE_USED_NDVI = 0.3
MOCK_PROVIDER = "mock-sentinel-2"

EvidenceKind = Literal["INSPECTOR_PHOTO", "OWNER_REPORT", "SATELLITE"]


class EvidenceItem(ApiModel):
    kind: EvidenceKind
    ok: bool
    at: datetime | None
    detail: str | None


class ResolutionEvidence(ApiModel):
    since: datetime | None
    sufficient: bool
    items: list[EvidenceItem]


async def _since(session: AsyncSession, parcel: Parcel) -> datetime | None:
    return await session.scalar(
        select(func.max(StatusTransition.created_at)).where(
            StatusTransition.entity_type == EntityType.PARCEL,
            StatusTransition.entity_id == parcel.id,
            StatusTransition.to_status.in_([ParcelStatus.IN_REMEDIATION.value, ParcelStatus.VIOLATION.value]),
        )
    )


async def resolution_evidence(session: AsyncSession, parcel: Parcel) -> ResolutionEvidence:
    since = await _since(session, parcel)
    items: list[EvidenceItem] = []

    # 1. Inspector photo taken on the parcel after the precept.
    parcel_boundary = select(cast(Parcel.geometry, Geography)).where(Parcel.id == parcel.id).scalar_subquery()
    photo_query = (
        select(Photo.created_at, func.coalesce(Photo.taken_at, Photo.created_at))
        .where(
            Photo.owner_type == PhotoOwnerType.PARCEL,
            Photo.owner_id == parcel.id,
            Photo.source == PhotoSource.INSPECTOR,
            Photo.location.is_not(None),
            func.ST_DWithin(cast(Photo.location, Geography), parcel_boundary, EVIDENCE_RADIUS_M),
        )
        .order_by(Photo.created_at.desc())
        .limit(1)
    )
    if since is not None:
        photo_query = photo_query.where(func.coalesce(Photo.taken_at, Photo.created_at) >= since)
    photo = (await session.execute(photo_query)).first()
    items.append(
        EvidenceItem(
            kind="INSPECTOR_PHOTO", ok=photo is not None, at=photo[1] if photo else None, detail=None
        )
    )

    # 2. Accepted owner photo report after the precept.
    report_query = (
        select(InspectionRequest.code, InspectionRequest.submitted_at)
        .where(
            InspectionRequest.parcel_id == parcel.id, InspectionRequest.status == InspectionStatus.ACCEPTED
        )
        .order_by(InspectionRequest.submitted_at.desc())
        .limit(1)
    )
    if since is not None:
        report_query = report_query.where(InspectionRequest.submitted_at >= since)
    report = (await session.execute(report_query)).first()
    items.append(
        EvidenceItem(
            kind="OWNER_REPORT",
            ok=report is not None,
            at=report[1] if report else None,
            detail=report[0] if report else None,
        )
    )

    # 3. Satellite: only meaningful for unused land (vegetation proves the land is worked).
    if parcel.violation_type is ViolationType.UNUSED:
        scan_query = (
            select(NdviScan.observed_at, NdviScan.ndvi, NdviScan.scene_id)
            .where(
                NdviScan.parcel_id == parcel.id,
                NdviScan.provider != MOCK_PROVIDER,
                NdviScan.observed_at.is_not(None),
            )
            .order_by(NdviScan.observed_at.desc())
            .limit(1)
        )
        if since is not None:
            scan_query = scan_query.where(NdviScan.observed_at >= since)
        scan = (await session.execute(scan_query)).first()
        items.append(
            EvidenceItem(
                kind="SATELLITE",
                ok=bool(scan and scan[1] >= SATELLITE_USED_NDVI),
                at=scan[0] if scan else None,
                detail=f"NDVI {scan[1]:.2f} · {scan[2]}" if scan else None,
            )
        )

    return ResolutionEvidence(since=since, sufficient=any(i.ok for i in items), items=items)
