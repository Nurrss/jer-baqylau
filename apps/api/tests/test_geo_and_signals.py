"""PostGIS behaviour: seed geometry quality, parcel binding, deduplication, rate limits."""

from __future__ import annotations

import math

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RateLimitedError, ValidationFailedError
from app.db.models import Parcel, Signal, StatusTransition
from app.domain.enums import AllocationStatus, EntityType, Lang, ParcelStatus, SignalCategory
from app.services import signals as service

M_PER_DEG_LAT = 111_132.0


async def _centroid(session: AsyncSession, cadastral: str) -> tuple[float, float, Parcel]:
    parcel = await session.scalar(select(Parcel).where(Parcel.cadastral_number == cadastral))
    assert parcel is not None
    lat, lon = (
        await session.execute(
            select(func.ST_Y(Parcel.centroid), func.ST_X(Parcel.centroid)).where(Parcel.id == parcel.id)
        )
    ).one()
    return lat, lon, parcel


def _shift(lat: float, lon: float, north_m: float = 0, east_m: float = 0) -> tuple[float, float]:
    return lat + north_m / M_PER_DEG_LAT, lon + east_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


async def _ok_parcel(session: AsyncSession) -> str:
    """An OK parcel with no signal within 100 m, so seeded signals can't interfere."""
    cadastral = await session.scalar(
        text(
            """
            SELECT p.cadastral_number FROM parcels p
             WHERE p.status = 'OK'
               AND NOT EXISTS (
                   SELECT 1 FROM signals s
                    WHERE ST_DWithin(s.location::geography, p.geometry::geography, 100))
          ORDER BY p.cadastral_number LIMIT 1
            """
        )
    )
    assert cadastral
    return cadastral


# ── Seed quality ────────────────────────────────────────────────────────────


async def test_seed_parcels_are_valid_and_do_not_overlap(session: AsyncSession) -> None:
    invalid = await session.scalar(select(func.count()).where(~func.ST_IsValid(Parcel.geometry)))
    assert invalid == 0
    overlaps = await session.scalar(
        text(
            """
            SELECT count(*) FROM parcels a JOIN parcels b
              ON a.id < b.id AND ST_Intersects(a.geometry, b.geometry)
             WHERE ST_Area(ST_Intersection(a.geometry, b.geometry)::geography) > 0.01
            """
        )
    )
    assert overlaps == 0


async def test_seed_distribution_and_areas(session: AsyncSession) -> None:
    monitored = Parcel.allocation_status == AllocationStatus.NONE
    total = await session.scalar(select(func.count(Parcel.id)).where(monitored))
    assert 40 <= (total or 0) <= 60
    fund = await session.scalar(
        select(func.count(Parcel.id)).where(Parcel.allocation_status == AllocationStatus.OFFERED)
    )
    assert (fund or 0) >= 15  # free state land for the Mini App
    rows = dict(
        (await session.execute(select(Parcel.status, func.count()).where(monitored).group_by(Parcel.status)))
        .tuples()
        .all()
    )
    green = rows.get(ParcelStatus.OK, 0) + rows.get(ParcelStatus.RESOLVED, 0)
    red = rows.get(ParcelStatus.VIOLATION, 0) + rows.get(ParcelStatus.IN_REMEDIATION, 0)
    assert 0.5 <= green / total <= 0.7
    assert 0.15 <= red / total <= 0.25
    assert rows.get(ParcelStatus.RETURNED_TO_STATE, 0) >= 2
    izhs = (
        await session.execute(
            select(func.min(Parcel.area_ha), func.max(Parcel.area_ha)).where(Parcel.purpose == "IZHS")
        )
    ).one()
    agro = (
        await session.execute(
            select(func.min(Parcel.area_ha), func.max(Parcel.area_ha)).where(Parcel.purpose == "AGRICULTURE")
        )
    ).one()
    assert float(izhs[0]) >= 0.06
    assert float(izhs[1]) <= 0.15
    assert float(agro[0]) >= 5
    assert float(agro[1]) <= 50


# ── Parcel binding ──────────────────────────────────────────────────────────


async def test_point_inside_parcel_binds_with_zero_distance(session: AsyncSession) -> None:
    cadastral = await _ok_parcel(session)
    lat, lon, parcel = await _centroid(session, cadastral)
    match = await service.find_parcel(session, lat, lon)
    assert match is not None
    assert match.parcel_id == parcel.id
    assert match.distance_m == 0


async def test_point_outside_binds_to_nearest_within_100m(session: AsyncSession) -> None:
    # The northernmost vertex of an agricultural block: 30 m further north is outside every parcel.
    lon, lat = (
        await session.execute(
            text(
                """
                SELECT ST_X(pt.geom), ST_Y(pt.geom)
                  FROM parcels, LATERAL ST_DumpPoints(geometry) AS pt
                 WHERE cadastral_number LIKE '06:097:904:%'
              ORDER BY ST_Y(pt.geom) DESC LIMIT 1
                """
            )
        )
    ).one()
    near = await service.find_parcel(session, *_shift(lat, lon, north_m=30))
    assert near is not None
    assert 25 <= near.distance_m <= 35
    assert await service.find_parcel(session, *_shift(lat, lon, north_m=150)) is None


async def test_signal_marks_ok_parcel_under_check_and_audits(session: AsyncSession) -> None:
    cadastral = await _ok_parcel(session)
    lat, lon, parcel = await _centroid(session, cadastral)
    signal = await service.create_signal(
        session,
        lat=lat,
        lon=lon,
        category=SignalCategory.DUMP,
        description="  мусор  ",
        reporter_chat_id=900001,
        reporter_lang=Lang.KK,
    )
    assert signal.parcel_id == parcel.id
    assert signal.description == "мусор"
    assert signal.tracking_code.startswith("SIG-")
    await session.refresh(parcel)
    assert parcel.status is ParcelStatus.UNDER_CHECK
    audit = await session.scalar(
        select(StatusTransition)
        .where(StatusTransition.entity_type == EntityType.PARCEL, StatusTransition.entity_id == parcel.id)
        .order_by(StatusTransition.id.desc())
    )
    assert audit is not None
    assert audit.to_status == "UNDER_CHECK"
    assert audit.meta["signal_code"] == signal.tracking_code


async def test_duplicate_within_30m_links_to_root(session: AsyncSession) -> None:
    cadastral = await _ok_parcel(session)
    lat, lon, _ = await _centroid(session, cadastral)
    root = await service.create_signal(
        session,
        lat=lat,
        lon=lon,
        category=SignalCategory.DUMP,
        description=None,
        reporter_chat_id=900002,
        reporter_lang=Lang.RU,
    )
    dup = await service.create_signal(
        session,
        lat=_shift(lat, lon, north_m=12)[0],
        lon=lon,
        category=SignalCategory.DUMP,
        description=None,
        reporter_chat_id=900003,
        reporter_lang=Lang.RU,
    )
    far_lat, far_lon = _shift(lat, lon, north_m=45)
    separate = await service.create_signal(
        session,
        lat=far_lat,
        lon=far_lon,
        category=SignalCategory.DUMP,
        description=None,
        reporter_chat_id=900004,
        reporter_lang=Lang.RU,
    )
    assert root.duplicate_of is None
    assert dup.duplicate_of == root.id
    assert separate.duplicate_of is None


async def test_out_of_region_rejected(session: AsyncSession) -> None:
    with pytest.raises(ValidationFailedError) as exc:
        await service.create_signal(
            session,
            lat=51.13,
            lon=71.43,
            category=SignalCategory.OTHER,
            description=None,
            reporter_chat_id=None,
            reporter_lang=Lang.RU,
        )
    assert exc.value.code == "OUT_OF_REGION"


async def test_rate_limit_per_chat(session: AsyncSession) -> None:
    lat, lon, _ = await _centroid(session, "06:097:904:011")
    for i in range(5):
        await service.create_signal(
            session,
            lat=_shift(lat, lon, east_m=i * 50)[0],
            lon=lon,
            category=SignalCategory.OTHER,
            description=None,
            reporter_chat_id=900005,
            reporter_lang=Lang.RU,
        )
    with pytest.raises(RateLimitedError):
        await service.create_signal(
            session,
            lat=lat,
            lon=lon,
            category=SignalCategory.OTHER,
            description=None,
            reporter_chat_id=900005,
            reporter_lang=Lang.RU,
        )
    count = await session.scalar(select(func.count(Signal.id)).where(Signal.reporter_chat_id == 900005))
    assert count == 5
