"""Periodic satellite scan: NDVI per parcel, flag probably-unused land."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import NdviScan, Parcel
from app.domain.enums import EventType, ParcelStatus
from app.providers.satellite import ParcelSnapshot, SatelliteProvider
from app.schemas.misc import NdviLayer, NdviReadingOut, SatelliteScanResult
from app.services import audit

log = get_logger(__name__)


async def run_scan(session: AsyncSession, provider: SatelliteProvider) -> SatelliteScanResult:
    parcels = list(
        await session.scalars(select(Parcel).where(Parcel.status != ParcelStatus.RETURNED_TO_STATE))
    )
    snapshots = [
        ParcelSnapshot(
            id=str(p.id),
            cadastral_number=p.cadastral_number,
            purpose=p.purpose,
            status=p.status,
            violation_type=p.violation_type,
        )
        for p in parcels
    ]
    now = datetime.now(UTC)
    readings = await provider.ndvi(snapshots, now)
    by_id = {str(p.id): p for p in parcels}
    flagged = 0
    for reading in readings:
        parcel = by_id[reading.parcel_id]
        session.add(
            NdviScan(parcel_id=parcel.id, ndvi=reading.ndvi, flagged=reading.flagged, provider=provider.name)
        )
        parcel.ndvi = reading.ndvi
        parcel.ndvi_flagged = reading.flagged
        parcel.ndvi_scanned_at = now
        flagged += int(reading.flagged)
    await audit.emit_event(
        session,
        EventType.SATELLITE_SCAN_COMPLETED,
        {"provider": provider.name, "scanned": len(readings), "flagged": flagged},
    )
    await session.flush()
    log.info("satellite_scan_completed", scanned=len(readings), flagged=flagged, provider=provider.name)
    return SatelliteScanResult(scanned=len(readings), flagged=flagged, provider=provider.name)


async def layer(session: AsyncSession, provider: SatelliteProvider) -> NdviLayer:
    rows = (
        await session.execute(
            select(Parcel.id, Parcel.ndvi, Parcel.ndvi_flagged, Parcel.ndvi_scanned_at).where(
                Parcel.ndvi.is_not(None)
            )
        )
    ).all()
    scanned_at = max((r.ndvi_scanned_at for r in rows if r.ndvi_scanned_at), default=None)
    return NdviLayer(
        provider=provider.name,
        is_demo=provider.is_demo,
        scanned_at=scanned_at,
        threshold=provider.threshold,
        readings=[
            NdviReadingOut(
                parcel_id=str(r.id), ndvi=r.ndvi, flagged=r.ndvi_flagged, scanned_at=r.ndvi_scanned_at
            )
            for r in rows
        ],
    )
