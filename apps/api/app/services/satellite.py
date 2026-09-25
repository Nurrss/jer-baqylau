"""Periodic satellite scan: NDVI per parcel, flag probably-unused land."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import NdviScan, Parcel
from app.domain.enums import EventType, ParcelStatus
from app.providers.satellite import ParcelSnapshot, SatelliteProvider
from app.schemas.misc import NdviLayer, NdviReadingOut, SatelliteScanResult
from app.services import audit

log = get_logger(__name__)


async def run_scan(session: AsyncSession, provider: SatelliteProvider) -> SatelliteScanResult:
    rows = (
        await session.execute(
            select(Parcel, func.ST_AsGeoJSON(Parcel.geometry, 7)).where(
                Parcel.status != ParcelStatus.RETURNED_TO_STATE
            )
        )
    ).all()
    snapshots = [
        ParcelSnapshot(
            id=str(p.id),
            cadastral_number=p.cadastral_number,
            purpose=p.purpose,
            status=p.status,
            violation_type=p.violation_type,
            geometry=json.loads(geojson),
        )
        for p, geojson in rows
    ]
    now = datetime.now(UTC)
    readings = await provider.ndvi(snapshots, now)
    by_id = {str(p.id): p for p, _ in rows}
    flagged = 0
    for reading in readings:
        parcel = by_id[reading.parcel_id]
        session.add(
            NdviScan(
                parcel_id=parcel.id,
                ndvi=reading.ndvi,
                flagged=reading.flagged,
                provider=provider.name,
                observed_at=reading.observed_at,
                scene_id=reading.scene_id,
                valid_fraction=reading.valid_fraction,
            )
        )
        # Parcels without a clear view keep their previous value (a cloudy week must not erase data).
        parcel.ndvi = reading.ndvi
        parcel.ndvi_flagged = reading.flagged
        parcel.ndvi_scanned_at = now
        parcel.ndvi_observed_at = reading.observed_at
        parcel.ndvi_scene_id = reading.scene_id
        flagged += int(reading.flagged)
    scenes = sorted({r.scene_id for r in readings if r.scene_id})
    await audit.emit_event(
        session,
        EventType.SATELLITE_SCAN_COMPLETED,
        {"provider": provider.name, "scanned": len(readings), "flagged": flagged, "scenes": scenes},
    )
    await session.flush()
    log.info(
        "satellite_scan_completed",
        scanned=len(readings),
        of=len(snapshots),
        flagged=flagged,
        provider=provider.name,
        scenes=scenes,
    )
    return SatelliteScanResult(scanned=len(readings), flagged=flagged, provider=provider.name)


async def layer(session: AsyncSession, provider: SatelliteProvider) -> NdviLayer:
    rows = (
        await session.execute(
            select(
                Parcel.id,
                Parcel.ndvi,
                Parcel.ndvi_flagged,
                Parcel.ndvi_scanned_at,
                Parcel.ndvi_observed_at,
                Parcel.ndvi_scene_id,
            ).where(Parcel.ndvi.is_not(None))
        )
    ).all()
    scanned_at = max((r.ndvi_scanned_at for r in rows if r.ndvi_scanned_at), default=None)
    observed = [r.ndvi_observed_at for r in rows if r.ndvi_observed_at]
    return NdviLayer(
        provider=provider.name,
        is_demo=provider.is_demo,
        scanned_at=scanned_at,
        observed_from=min(observed, default=None),
        observed_to=max(observed, default=None),
        scenes=sorted({r.ndvi_scene_id for r in rows if r.ndvi_scene_id}),
        threshold=provider.threshold,
        readings=[
            NdviReadingOut(
                parcel_id=str(r.id),
                ndvi=r.ndvi,
                flagged=r.ndvi_flagged,
                scanned_at=r.ndvi_scanned_at,
                observed_at=r.ndvi_observed_at,
                scene_id=r.ndvi_scene_id,
            )
            for r in rows
        ],
    )
