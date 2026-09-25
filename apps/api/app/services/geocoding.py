"""Reverse geocoding via Nominatim with a database cache and coordinate fallback."""

from __future__ import annotations

import asyncio
import time

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import GeocodeCache
from app.domain.enums import Lang

log = get_logger(__name__)

TIMEOUT_SECONDS = 4.0
# Nominatim usage policy: at most 1 request per second.
_lock = asyncio.Lock()
_last_request = 0.0


def cache_key(lat: float, lon: float) -> str:
    return f"{lat:.4f},{lon:.4f}"


def format_coords(lat: float, lon: float) -> str:
    return f"{lat:.5f}, {lon:.5f}"


def _short_address(data: dict[str, object]) -> str | None:
    address = data.get("address")
    if not isinstance(address, dict):
        name = data.get("display_name")
        return str(name) if name else None
    road = address.get("road") or address.get("pedestrian") or address.get("neighbourhood")
    house = address.get("house_number")
    place = (
        address.get("city") or address.get("town") or address.get("village") or address.get("hamlet")
        or address.get("county")
    )  # fmt: skip
    parts = [p for p in (place, road, house) if p]
    return ", ".join(str(p) for p in parts) or (
        str(data.get("display_name")) if data.get("display_name") else None
    )


async def _fetch(lat: float, lon: float, lang: Lang) -> str | None:
    global _last_request
    settings = get_settings()
    async with _lock:
        wait = 1.0 - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request = time.monotonic()
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{settings.nominatim_url.rstrip('/')}/reverse",
                params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 1},
                headers={"User-Agent": settings.nominatim_user_agent, "Accept-Language": f"{lang.value},ru"},
            )
    resp.raise_for_status()
    return _short_address(resp.json())


async def reverse(session: AsyncSession, lat: float, lon: float, lang: Lang) -> str:
    """Human-readable address; falls back to coordinates if Nominatim is unavailable."""
    key = cache_key(lat, lon)
    cached = await session.scalar(select(GeocodeCache).where(GeocodeCache.key == key))
    if cached is not None:
        value = cached.address_kk if lang is Lang.KK else cached.address_ru
        if value:
            return value
    try:
        address = await _fetch(lat, lon, lang)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("reverse_geocoding_failed", error=str(exc))
        address = None
    if not address:
        return format_coords(lat, lon)
    column = "address_kk" if lang is Lang.KK else "address_ru"
    await session.execute(
        insert(GeocodeCache)
        .values(key=key, **{column: address})
        .on_conflict_do_update(index_elements=[GeocodeCache.key], set_={column: address})
    )
    return address
