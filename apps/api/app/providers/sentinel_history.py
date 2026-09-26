"""Per-parcel Sentinel-2 history: monthly NDVI time series and true-colour image chips.

Used as evidence in a case: "the field has not been cultivated for three seasons" is shown as an
NDVI curve and as before/after images, not just asserted.

* History: all L2A scenes over the parcel for ``months`` months → per calendar month the clearest
  scenes are tried (lowest cloud first) until one gives a clear view of the parcel.
* Chips: the ``visual`` asset (8-bit true colour, 10 m) around the parcel, upscaled to a square PNG
  with the parcel outline drawn on top.
"""

from __future__ import annotations

import io
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
from shapely.geometry import shape

from app.core.logging import get_logger
from app.providers.sentinel import (
    COLLECTION,
    GDAL_ENV,
    WINDOW_PAD_M,
    effective_offset,
    parcel_ndvi_stats,
    read_scene_windows,
)

log = get_logger(__name__)

MIN_VALID_FRACTION = 0.6
CANDIDATES_PER_MONTH = 3
MAX_PAGES = 6
HISTORY_WORKERS = 3  # same as the periodic scan: fits a 512 MB container
CHIP_SIZE_PX = 320
CHIP_MIN_EXTENT_M = 300  # small house plots still get visible context


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    observed_at: datetime
    scene_id: str
    ndvi: float
    valid_fraction: float


async def search_scenes(
    stac_url: str,
    bbox: tuple[float, float, float, float],
    start: datetime,
    end: datetime,
    max_cloud: float = 60,
) -> list[dict[str, Any]]:
    """All scenes over ``bbox`` in the period (follows STAC ``next`` pagination)."""
    body: dict[str, Any] | None = {
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": 100,
    }
    url = f"{stac_url.rstrip('/')}/search"
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=40) as client:
        for _ in range(MAX_PAGES):
            if body is None:
                break
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            page = resp.json()
            items.extend(page.get("features", []))
            nxt = next((link for link in page.get("links", []) if link.get("rel") == "next"), None)
            body = nxt.get("body") if nxt else None
            url = nxt.get("href", url) if nxt else url
    return items


def _crs(item: dict[str, Any]) -> str:
    props = item["properties"]
    return str(props.get("proj:code") or f"EPSG:{props.get('proj:epsg')}")


def _observed(item: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))


def parcel_point(item: dict[str, Any], geometry: dict[str, Any]) -> HistoryPoint | None:
    """NDVI of one parcel in one scene, or None if the parcel is not clearly visible."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom

    band = item["assets"]["red"].get("raster:bands", [{}])[0]
    scale, offset = float(band.get("scale", 0.0001)), float(band.get("offset", -0.1))
    with rasterio.Env(**GDAL_ENV):
        geom = transform_geom("EPSG:4326", _crs(item), geometry)
        minx, miny, maxx, maxy = shape(geom).bounds
        bounds = (minx - WINDOW_PAD_M, miny - WINDOW_PAD_M, maxx + WINDOW_PAD_M, maxy + WINDOW_PAD_M)
        [window] = read_scene_windows(item, [bounds])
    mask = geometry_mask([geom], out_shape=window.red.shape, transform=window.transform, invert=True)
    if not mask.any():
        mask = geometry_mask(
            [geom], out_shape=window.red.shape, transform=window.transform, invert=True, all_touched=True
        )
    applied = effective_offset(window.red, window.scl, scale, offset)
    stat = parcel_ndvi_stats(window.red, window.nir, window.scl, {"p": mask}, scale, applied).get("p")
    if stat is None or stat.valid_fraction < MIN_VALID_FRACTION or np.isnan(stat.ndvi):
        return None
    return HistoryPoint(_observed(item), item["id"], stat.ndvi, stat.valid_fraction)


def monthly_candidates(
    items: list[dict[str, Any]], geometry: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Scenes covering the parcel grouped by month, clearest first."""
    centroid = shape(geometry).centroid
    months: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not shape(item["geometry"]).contains(centroid):
            continue
        observed = _observed(item)
        key = (f"{observed:%Y-%m-%d}", item["id"].split("_")[1])  # same day + tile → one scene
        if key in seen:
            continue
        seen.add(key)
        months[f"{observed:%Y-%m}"].append(item)
    return {
        month: sorted(scenes, key=lambda i: i["properties"].get("eo:cloud_cover", 100))[:CANDIDATES_PER_MONTH]
        for month, scenes in months.items()
    }


def _best_for_month(candidates: list[dict[str, Any]], geometry: dict[str, Any]) -> HistoryPoint | None:
    for item in candidates:
        try:
            point = parcel_point(item, geometry)
        except Exception as exc:  # a broken COG must not stop the series
            log.warning("sentinel_history_scene_failed", scene=item["id"], error=str(exc))
            continue
        if point is not None:
            log.info("sentinel_history_month", scene=item["id"], rss_mb=_rss_mb())
            return point
    return None


def _rss_mb() -> int:
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024  # Linux: KiB


async def ndvi_history(
    stac_url: str, geometry: dict[str, Any], end: datetime, months: int = 36
) -> list[HistoryPoint]:
    import asyncio

    start = end - timedelta(days=int(months * 30.44))
    bbox = shape(geometry).bounds
    items = await search_scenes(stac_url, bbox, start, end)
    by_month = monthly_candidates(items, geometry)

    def run() -> list[HistoryPoint]:
        with ThreadPoolExecutor(max_workers=HISTORY_WORKERS) as pool:
            results = pool.map(lambda c: _best_for_month(c, geometry), by_month.values())
            return sorted((p for p in results if p is not None), key=lambda p: p.observed_at)

    points = await asyncio.to_thread(run)
    log.info(
        "sentinel_history_built",
        scenes=len(items),
        months=len(by_month),
        points=len(points),
        peak_rss_mb=_rss_mb(),
    )
    return points


def render_chip(item: dict[str, Any], geometry: dict[str, Any], size: int = CHIP_SIZE_PX) -> bytes:
    """True-colour PNG around the parcel with its outline (for before/after comparison)."""
    import rasterio
    from PIL import Image, ImageDraw
    from rasterio.enums import Resampling
    from rasterio.warp import transform_geom
    from rasterio.windows import from_bounds

    with rasterio.Env(**GDAL_ENV):
        geom = transform_geom("EPSG:4326", _crs(item), geometry)
        minx, miny, maxx, maxy = shape(geom).bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        half = max(maxx - minx, maxy - miny, CHIP_MIN_EXTENT_M) * 0.75
        bounds = (cx - half, cy - half, cx + half, cy + half)
        with rasterio.open(item["assets"]["visual"]["href"]) as src:
            window = from_bounds(*bounds, transform=src.transform)
            rgb = src.read(
                (1, 2, 3),
                window=window,
                out_shape=(3, size, size),
                resampling=Resampling.bilinear,
                boundless=True,
            )
    image = Image.fromarray(np.moveaxis(rgb, 0, -1).astype("uint8"), "RGB")

    def to_px(x: float, y: float) -> tuple[float, float]:
        return ((x - bounds[0]) / (2 * half) * size, (bounds[3] - y) / (2 * half) * size)

    draw = ImageDraw.Draw(image)
    polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for polygon in polygons:
        ring = [to_px(x, y) for x, y in polygon[0]]
        draw.line([*ring, ring[0]], fill=(255, 214, 0), width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
