"""Satellite evidence for one parcel: NDVI history (up to 3 years) and before/after image chips.

Building the history reads dozens of Sentinel-2 scenes, so it runs once in the background and is
stored in ``ndvi_scans``; the API returns ``status=loading`` meanwhile and the panel is notified by
a ``satellite.history_ready`` event.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import NdviScan, Parcel
from app.db.session import session_scope
from app.domain.enums import EventType, ParcelPurpose, ViolationType
from app.providers.satellite import UNUSED_NDVI_THRESHOLD, get_satellite_provider
from app.providers.storage import StorageProvider, get_storage
from app.schemas.parcels import NdviPoint, ParcelSatellite, SatelliteImage, YearPeak
from app.services import audit

log = get_logger(__name__)

HISTORY_PROVIDER = "sentinel-2-l2a:history"
HISTORY_MONTHS = 36
CHIP_TARGETS_DAYS = (0, 365, 730)  # now, a year ago, two years ago
GROWING_MONTHS = range(5, 9)  # May–August: differences between used and unused land are largest

_in_progress: set[uuid.UUID] = set()
_tasks: set[asyncio.Task[None]] = set()
# One heavy raster job at a time; a finished (or failed) attempt is not repeated for a while,
# so a panel polling a parcel without usable scenes does not restart the download every 5 s.
_job_slot = asyncio.Semaphore(1)
_last_attempt: dict[uuid.UUID, datetime] = {}
RETRY_AFTER = timedelta(minutes=30)


def _yearly_peaks(points: list[NdviPoint]) -> list[YearPeak]:
    peaks: dict[int, float] = {}
    for point in points:
        peaks[point.date.year] = max(peaks.get(point.date.year, -1.0), point.ndvi)
    return [YearPeak(year=year, peak=round(value, 3)) for year, value in sorted(peaks.items())]


def _demo_series(parcel: Parcel, now: datetime) -> list[NdviPoint]:
    """Deterministic seasonal curve for the offline demo provider."""
    seed = int(uuid.uuid5(uuid.NAMESPACE_URL, parcel.cadastral_number).hex[:6], 16) / 0xFFFFFF
    unused = parcel.violation_type is ViolationType.UNUSED or (
        parcel.ndvi_flagged and parcel.ndvi is not None
    )
    amplitude = 0.05 if unused else (0.45 if parcel.purpose is ParcelPurpose.AGRICULTURE else 0.25)
    base = 0.12 if unused else 0.2 + seed * 0.1
    points = []
    for months_back in range(HISTORY_MONTHS, -1, -1):
        date = now - timedelta(days=int(months_back * 30.44))
        season = math.sin((date.month - 3) / 12 * 2 * math.pi)
        value = base + amplitude * max(season, 0) + (seed - 0.5) * 0.03
        points.append(NdviPoint(date=date, ndvi=round(min(value, 0.9), 3), valid_fraction=1.0, scene_id=None))
    return points


def _choose_chip_rows(rows: list[NdviScan]) -> list[NdviScan]:
    """Latest clear scene plus the ones closest to one and two years earlier (growing season preferred)."""
    dated = [(r.observed_at, r) for r in rows if r.observed_at is not None and r.scene_id]
    if not dated:
        return []
    latest_at = max(at for at, _ in dated)
    chosen: list[NdviScan] = []
    for days in CHIP_TARGETS_DAYS:
        target = latest_at - timedelta(days=days)
        pool = [(at, r) for at, r in dated if r not in chosen]
        if days:
            pool = [(at, r) for at, r in pool if at.month in GROWING_MONTHS] or pool
        if not pool:
            break
        best_at, best = min(pool, key=lambda pair: abs((pair[0] - target).days))
        if days and abs((best_at - target).days) > 150:
            continue
        chosen.append(best)
    return chosen


async def get_satellite(
    session: AsyncSession, storage: StorageProvider, parcel_id: uuid.UUID
) -> ParcelSatellite:
    parcel = await session.get(Parcel, parcel_id)
    if parcel is None:
        raise NotFoundError("Parcel not found", details={"parcel_id": str(parcel_id)})
    provider = get_satellite_provider()
    if provider.is_demo:
        points = _demo_series(parcel, datetime.now(UTC))
        return ParcelSatellite(
            status="demo",
            provider=provider.name,
            is_demo=True,
            threshold=provider.threshold,
            points=points,
            yearly_peaks=_yearly_peaks(points),
            images=[],
        )

    rows = list(
        await session.scalars(
            select(NdviScan)
            .where(NdviScan.parcel_id == parcel_id, NdviScan.observed_at.is_not(None))
            .order_by(NdviScan.observed_at)
        )
    )
    has_history = any(r.provider == HISTORY_PROVIDER for r in rows)
    if not has_history:
        start_history_job(parcel_id)

    by_scene: dict[str, NdviScan] = {}
    for row in rows:
        by_scene.setdefault(row.scene_id or f"{row.id}", row)
    dated = sorted(((r.observed_at, r) for r in by_scene.values() if r.observed_at), key=lambda p: p[0])
    points = [
        NdviPoint(date=at, ndvi=r.ndvi, valid_fraction=r.valid_fraction, scene_id=r.scene_id)
        for at, r in dated
    ]
    chips = sorted(
        ((r.observed_at, r.chip_path, r.scene_id or "") for r in rows if r.chip_path and r.observed_at),
        key=lambda c: c[0],
        reverse=True,
    )
    urls = await storage.signed_urls([path for _, path, _ in chips])
    images = [
        SatelliteImage(date=at, scene_id=scene, url=urls[path]) for at, path, scene in chips if path in urls
    ]
    status = "loading" if parcel_id in _in_progress else "ready"
    return ParcelSatellite(
        status=status,
        provider=provider.name,
        is_demo=False,
        threshold=provider.threshold or UNUSED_NDVI_THRESHOLD,
        points=points,
        yearly_peaks=_yearly_peaks(points),
        images=images,
    )


def start_history_job(parcel_id: uuid.UUID) -> bool:
    if parcel_id in _in_progress:
        return False
    last = _last_attempt.get(parcel_id)
    if last is not None and datetime.now(UTC) - last < RETRY_AFTER:
        return False
    _last_attempt[parcel_id] = datetime.now(UTC)
    _in_progress.add(parcel_id)
    task = asyncio.create_task(_build_history(parcel_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def _fetch_item(client: httpx.AsyncClient, stac_url: str, scene_id: str) -> dict[str, Any]:
    resp = await client.get(f"{stac_url.rstrip('/')}/collections/sentinel-2-l2a/items/{scene_id}")
    resp.raise_for_status()
    return dict(resp.json())


async def _build_history(parcel_id: uuid.UUID) -> None:
    async with _job_slot:
        await _build_history_now(parcel_id)


async def _build_history_now(parcel_id: uuid.UUID) -> None:
    from app.providers.sentinel_history import ndvi_history, render_chip

    settings = get_settings()
    storage = get_storage()
    started = datetime.now(UTC)
    try:
        async with session_scope() as session:
            geojson = await session.scalar(
                select(func.ST_AsGeoJSON(Parcel.geometry, 7)).where(Parcel.id == parcel_id)
            )
        if geojson is None:
            return
        geometry = json.loads(geojson)
        points = await ndvi_history(settings.sentinel_stac_url, geometry, started, HISTORY_MONTHS)

        async with session_scope() as session:
            known = set(
                await session.scalars(
                    select(NdviScan.scene_id).where(
                        NdviScan.parcel_id == parcel_id, NdviScan.scene_id.is_not(None)
                    )
                )
            )
            for point in points:
                if point.scene_id in known:
                    continue
                session.add(
                    NdviScan(
                        parcel_id=parcel_id,
                        ndvi=point.ndvi,
                        flagged=point.ndvi < UNUSED_NDVI_THRESHOLD,
                        provider=HISTORY_PROVIDER,
                        observed_at=point.observed_at,
                        scene_id=point.scene_id,
                        valid_fraction=point.valid_fraction,
                    )
                )
            await session.flush()
            rows = list(
                await session.scalars(
                    select(NdviScan).where(NdviScan.parcel_id == parcel_id, NdviScan.scene_id.is_not(None))
                )
            )
            chosen = _choose_chip_rows(rows)

            async with httpx.AsyncClient(timeout=30) as client:
                for row in chosen:
                    if row.chip_path or not row.scene_id:
                        continue
                    try:
                        item = await _fetch_item(client, settings.sentinel_stac_url, row.scene_id)
                        png = await asyncio.to_thread(render_chip, item, geometry)
                        path = f"imagery/{parcel_id}/{row.scene_id}.png"
                        await storage.upload(path, png, "image/png")
                        row.chip_path = path
                    except Exception as exc:
                        log.warning("satellite_chip_failed", scene=row.scene_id, error=str(exc))
            await audit.emit_event(
                session,
                EventType.SATELLITE_HISTORY_READY,
                {
                    "parcel_id": str(parcel_id),
                    "points": len(points),
                    "images": sum(1 for r in chosen if r.chip_path),
                },
            )
        log.info(
            "satellite_history_ready",
            parcel_id=str(parcel_id),
            points=len(points),
            seconds=round((datetime.now(UTC) - started).total_seconds(), 1),
        )
    except Exception:
        log.exception("satellite_history_failed", parcel_id=str(parcel_id))
    finally:
        _in_progress.discard(parcel_id)
