"""Dashboard, satellite layer, exports and the realtime-fallback event feed."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import CurrentInspector, DbSession
from app.db.models import Event, Parcel
from app.providers.satellite import get_satellite_provider
from app.schemas.common import ERROR_RESPONSES
from app.schemas.misc import DashboardStats, EventList, EventOut, NdviLayer, SatelliteScanStarted
from app.services import satellite, stats
from app.services.parcels import overdue_clause
from app.workers.scheduler import start_scan_in_background

router = APIRouter(responses=ERROR_RESPONSES)

EXPORT_COLUMNS = [
    "cadastral_number", "status", "violation_type", "purpose", "owner_type", "area_ha", "district",
    "address_ru", "address_kk", "lease_until", "deadline_at", "is_overdue", "ndvi", "ndvi_flagged",
    "centroid_lon", "centroid_lat",
]  # fmt: skip


@router.get("/stats/dashboard", response_model=DashboardStats, tags=["stats"])
async def dashboard(session: DbSession, _: CurrentInspector) -> DashboardStats:
    return await stats.dashboard(session)


@router.get(
    "/satellite/ndvi",
    response_model=NdviLayer,
    tags=["satellite"],
    summary="NDVI layer (Sentinel-2 L2A or demo provider)",
)
async def ndvi_layer(session: DbSession, _: CurrentInspector) -> NdviLayer:
    return await satellite.layer(session, get_satellite_provider())


@router.post(
    "/satellite/scan",
    response_model=SatelliteScanStarted,
    status_code=202,
    tags=["satellite"],
    summary="Start a satellite scan in the background (result arrives as a satellite.scan_completed event)",
)
async def satellite_scan(_: CurrentInspector) -> SatelliteScanStarted:
    provider = get_satellite_provider()
    started = start_scan_in_background()
    return SatelliteScanStarted(started=started, provider=provider.name, is_demo=provider.is_demo)


@router.get("/events", response_model=EventList, tags=["events"], summary="Event feed (realtime fallback)")
async def list_events(
    session: DbSession,
    _: CurrentInspector,
    since: Annotated[int | None, Query(ge=0, description="Return events with id > since")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> EventList:
    if since is None:
        last_id = await session.scalar(select(func.coalesce(func.max(Event.id), 0)))
        return EventList(items=[], last_id=int(last_id or 0))
    rows = list(await session.scalars(select(Event).where(Event.id > since).order_by(Event.id).limit(limit)))
    return EventList(items=[EventOut.model_validate(r) for r in rows], last_id=rows[-1].id if rows else since)


async def _export_rows(session: DbSession) -> list[tuple[Parcel, str, bool, float, float]]:
    now = datetime.now(UTC)
    result = await session.execute(
        select(
            Parcel,
            func.ST_AsGeoJSON(Parcel.geometry, 6),
            overdue_clause(now),
            func.ST_X(Parcel.centroid),
            func.ST_Y(Parcel.centroid),
        ).order_by(Parcel.cadastral_number)
    )
    return [tuple(r) for r in result.all()]


def _record(parcel: Parcel, is_overdue: bool, lon: float, lat: float) -> dict[str, object]:
    return {
        "cadastral_number": parcel.cadastral_number,
        "status": parcel.status.value,
        "violation_type": parcel.violation_type.value if parcel.violation_type else None,
        "purpose": parcel.purpose.value,
        "owner_type": parcel.owner_type.value,
        "area_ha": float(parcel.area_ha),
        "district": parcel.district,
        "address_ru": parcel.address_ru,
        "address_kk": parcel.address_kk,
        "lease_until": parcel.lease_until.isoformat() if parcel.lease_until else None,
        "deadline_at": parcel.deadline_at.isoformat() if parcel.deadline_at else None,
        "is_overdue": bool(is_overdue),
        "ndvi": parcel.ndvi,
        "ndvi_flagged": parcel.ndvi_flagged,
        "centroid_lon": round(lon, 6),
        "centroid_lat": round(lat, 6),
    }


def _filename(ext: str) -> str:
    return f"parcels_{datetime.now(UTC):%Y%m%d_%H%M}.{ext}"


@router.get(
    "/export/parcels.geojson",
    tags=["export"],
    response_class=Response,
    responses={200: {"content": {"application/geo+json": {}}}},
)
async def export_geojson(session: DbSession, _: CurrentInspector) -> Response:
    features = [
        {"type": "Feature", "geometry": json.loads(geom), "properties": _record(p, overdue, lon, lat)}
        for p, geom, overdue, lon, lat in await _export_rows(session)
    ]
    body = json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)
    return Response(
        body,
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{_filename("geojson")}"'},
    )


@router.get(
    "/export/parcels.csv",
    tags=["export"],
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_csv(session: DbSession, _: CurrentInspector) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for p, _geom, overdue, lon, lat in await _export_rows(session):
        writer.writerow(_record(p, overdue, lon, lat))
    # BOM so Excel opens Cyrillic correctly.
    return Response(
        "﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename("csv")}"'},
    )
