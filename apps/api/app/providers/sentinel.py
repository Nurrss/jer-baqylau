"""Real Sentinel-2 L2A NDVI from the public Element84 Earth Search catalogue (AWS open data, no keys).

Algorithm (per scan):
1. STAC search: scenes over the parcels' extent for the last ``lookback_days``, cloud cover below
   ``max_cloud``, newest first.
2. For each scene (newest → oldest) take the parcels whose centroid lies in the scene footprint and
   still have no reading; read **one window** covering all of them from the red, nir (10 m) and SCL
   (20 m, resampled) Cloud-Optimized GeoTIFFs — a few HTTP range requests per band.
3. Per parcel: pixels inside the polygon that SCL marks as clear (vegetation, bare soil, water,
   unclassified); NDVI = mean((nir − red) / (nir + red)) on surface reflectance.
   A parcel is accepted if at least ``min_valid`` of its pixels are clear, otherwise an older
   scene is tried.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union

from app.core.logging import get_logger
from app.domain.enums import ParcelPurpose
from app.providers.satellite import UNUSED_NDVI_THRESHOLD, NdviReading, ParcelSnapshot

log = get_logger(__name__)

EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
# Scene classification (SCL) classes treated as a clear view of the ground.
CLEAR_SCL = (4, 5, 6, 7)  # vegetation, not vegetated, water, unclassified
WINDOW_PAD_M = 30
CLUSTER_CELL_M = 2000  # parcels within ~2 km share one read window
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "VSI_CACHE": "TRUE",
    # Containers see the host's RAM, so GDAL's default block cache (5 % of it) overshoots the
    # service memory limit when several worker threads read at once (OOM restarts).
    "GDAL_CACHEMAX": 96,  # MB, shared by all threads
}


@dataclass(frozen=True, slots=True)
class ParcelStat:
    ndvi: float
    valid_fraction: float


@dataclass(slots=True)
class SceneWindow:
    red: Any
    nir: Any
    scl: Any
    transform: Any


def read_scene_windows(
    item: dict[str, Any], bounds_list: list[tuple[float, float, float, float]]
) -> list[SceneWindow]:
    """Read several small windows (one per parcel cluster) from red, nir (10 m) and SCL (20 m → 10 m grid).

    Each band file is opened once; the three bands are read concurrently (independent COG range requests).
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds

    with rasterio.open(item["assets"]["red"]["href"]) as ref:
        windows = [
            from_bounds(*b, transform=ref.transform).round_offsets().round_lengths() for b in bounds_list
        ]
        transforms = [ref.window_transform(w) for w in windows]
    shapes = [(int(w.height), int(w.width)) for w in windows]

    def read(key: str) -> list[Any]:
        with rasterio.open(item["assets"][key]["href"]) as src:
            if key == "scl":
                return [
                    src.read(
                        1,
                        window=from_bounds(*b, transform=src.transform),
                        out_shape=shp,
                        resampling=Resampling.nearest,
                    )
                    for b, shp in zip(bounds_list, shapes, strict=True)
                ]
            return [src.read(1, window=w) for w in windows]

    with ThreadPoolExecutor(max_workers=3) as pool:
        reds, nirs, scls = pool.map(read, ("red", "nir", "scl"))
    return [SceneWindow(r, n, c, t) for r, n, c, t in zip(reds, nirs, scls, transforms, strict=True)]


def cluster_bounds(
    geoms: dict[str, Any], cell_m: float = CLUSTER_CELL_M
) -> list[tuple[list[str], tuple[float, float, float, float]]]:
    """Group projected parcel geometries into compact clusters; return (parcel ids, padded bounds) per cluster."""
    groups: dict[tuple[int, int], list[str]] = {}
    for parcel_id, geom in geoms.items():
        c = shape(geom).centroid
        groups.setdefault((int(c.x // cell_m), int(c.y // cell_m)), []).append(parcel_id)
    result = []
    for ids in groups.values():
        minx, miny, maxx, maxy = unary_union([shape(geoms[i]) for i in ids]).bounds
        result.append(
            (ids, (minx - WINDOW_PAD_M, miny - WINDOW_PAD_M, maxx + WINDOW_PAD_M, maxy + WINDOW_PAD_M))
        )
    return result


def effective_offset(
    red: np.ndarray[Any, Any], scl: np.ndarray[Any, Any], scale: float, offset: float
) -> float:
    """Apply the catalogue's BOA offset only if the data is physically consistent with it.

    Some Sentinel-2 L2A COGs declare ``offset = -0.1`` (processing baseline >= 04.00) although the
    pixel values are already harmonized: dark vegetation (red DN ~ 500) would then become a
    *negative* reflectance and NDVI explodes to 1. If more than 1 % of clear pixels would drop
    below zero, the offset is ignored.
    """
    if offset >= 0:
        return offset
    clear = np.isin(scl, CLEAR_SCL) & (red > 0)
    if not clear.any():
        return offset
    negative_share = float(((red[clear].astype("float32") * scale + offset) < 0).mean())
    return offset if negative_share <= 0.01 else 0.0


def parcel_ndvi_stats(
    red: np.ndarray[Any, Any],
    nir: np.ndarray[Any, Any],
    scl: np.ndarray[Any, Any],
    masks: dict[str, np.ndarray[Any, Any]],
    scale: float = 0.0001,
    offset: float = -0.1,
) -> dict[str, ParcelStat]:
    """Mean NDVI of clear pixels inside each parcel mask (pure function, unit-tested)."""
    red_r = red.astype("float32") * scale + offset
    nir_r = nir.astype("float32") * scale + offset
    denominator = nir_r + red_r
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denominator > 0, (nir_r - red_r) / denominator, np.nan)
    clear = np.isin(scl, CLEAR_SCL) & (red > 0) & (nir > 0) & np.isfinite(ndvi)
    result: dict[str, ParcelStat] = {}
    for parcel_id, mask in masks.items():
        total = int(mask.sum())
        if total == 0:
            continue
        valid = mask & clear
        n_valid = int(valid.sum())
        if n_valid == 0:
            result[parcel_id] = ParcelStat(ndvi=float("nan"), valid_fraction=0.0)
            continue
        result[parcel_id] = ParcelStat(
            ndvi=round(float(np.clip(np.nanmean(ndvi[valid]), -1, 1)), 3),
            valid_fraction=round(n_valid / total, 3),
        )
    return result


def _flagged(parcel: ParcelSnapshot, ndvi: float, threshold: float) -> bool:
    # Only land that is supposed to be cultivated can be "probably unused" by vegetation index.
    return parcel.purpose in (ParcelPurpose.AGRICULTURE, ParcelPurpose.LPH) and ndvi < threshold


class EarthSearchSentinelProvider:
    name = "sentinel-2-l2a"
    is_demo = False
    threshold = UNUSED_NDVI_THRESHOLD

    def __init__(
        self,
        stac_url: str = EARTH_SEARCH_URL,
        lookback_days: int = 45,
        max_cloud: float = 40,
        max_items: int = 12,
        min_valid: float = 0.5,
    ):
        self.stac_url = stac_url.rstrip("/")
        self.lookback_days = lookback_days
        self.max_cloud = max_cloud
        self.max_items = max_items
        self.min_valid = min_valid

    async def _search(self, bbox: tuple[float, float, float, float], at: datetime) -> list[dict[str, Any]]:
        start = at - timedelta(days=self.lookback_days)
        body = {
            "collections": [COLLECTION],
            "bbox": list(bbox),
            "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{at:%Y-%m-%dT%H:%M:%SZ}",
            "query": {"eo:cloud_cover": {"lt": self.max_cloud}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
            "limit": self.max_items,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.stac_url}/search", json=body)
            resp.raise_for_status()
            return list(resp.json().get("features", []))

    async def ndvi(self, parcels: list[ParcelSnapshot], at: datetime | None = None) -> list[NdviReading]:
        if not parcels:
            return []
        moment = at or datetime.now(UTC)
        extent = unary_union([shape(p.geometry) for p in parcels]).bounds
        items = await self._search(extent, moment)
        log.info("sentinel_scenes_found", count=len(items), ids=[i["id"] for i in items[:6]])
        return await asyncio.to_thread(self._compute, parcels, items)

    def _compute(self, parcels: list[ParcelSnapshot], items: list[dict[str, Any]]) -> list[NdviReading]:
        import rasterio
        from rasterio.features import geometry_mask
        from rasterio.warp import transform_geom

        remaining = {p.id: p for p in parcels}
        readings: list[NdviReading] = []
        with rasterio.Env(**GDAL_ENV):
            for item in items:
                if not remaining:
                    break
                footprint = shape(item["geometry"])
                batch = [p for p in remaining.values() if footprint.contains(shape(p.geometry).centroid)]
                if not batch:
                    continue
                props = item["properties"]
                crs = props.get("proj:code") or f"EPSG:{props.get('proj:epsg')}"
                observed = datetime.fromisoformat(props["datetime"].replace("Z", "+00:00"))
                band = item["assets"]["red"].get("raster:bands", [{}])[0]
                scale, offset = float(band.get("scale", 0.0001)), float(band.get("offset", -0.1))
                try:
                    geoms = {p.id: transform_geom("EPSG:4326", crs, p.geometry) for p in batch}
                    clusters = cluster_bounds(geoms)
                    windows = read_scene_windows(item, [bounds for _, bounds in clusters])
                except Exception as exc:  # network / COG errors: try the next scene
                    log.warning("sentinel_scene_read_failed", scene=item["id"], error=str(exc))
                    continue

                # One offset decision per scene, from all its clear pixels.
                applied_offset = effective_offset(
                    np.concatenate([w.red.ravel() for w in windows]),
                    np.concatenate([w.scl.ravel() for w in windows]),
                    scale,
                    offset,
                )
                if applied_offset != offset:
                    log.info("sentinel_offset_ignored", scene=item["id"], declared=offset)

                accepted = 0
                for (ids, _), window in zip(clusters, windows, strict=True):
                    masks = {}
                    for parcel_id in ids:
                        mask = geometry_mask(
                            [geoms[parcel_id]],
                            out_shape=window.red.shape,
                            transform=window.transform,
                            invert=True,
                        )
                        if not mask.any():  # tiny parcel: take every touched pixel
                            mask = geometry_mask(
                                [geoms[parcel_id]],
                                out_shape=window.red.shape,
                                transform=window.transform,
                                invert=True,
                                all_touched=True,
                            )
                        masks[parcel_id] = mask
                    stats = parcel_ndvi_stats(
                        window.red, window.nir, window.scl, masks, scale, applied_offset
                    )
                    for parcel_id, stat in stats.items():
                        if stat.valid_fraction < self.min_valid or np.isnan(stat.ndvi):
                            continue
                        parcel = remaining.pop(parcel_id)
                        readings.append(
                            NdviReading(
                                parcel_id=parcel_id,
                                ndvi=stat.ndvi,
                                flagged=_flagged(parcel, stat.ndvi, self.threshold),
                                observed_at=observed,
                                scene_id=item["id"],
                                valid_fraction=stat.valid_fraction,
                            )
                        )
                        accepted += 1
                log.info(
                    "sentinel_scene_processed",
                    scene=item["id"],
                    parcels=len(batch),
                    windows=len(windows),
                    accepted=accepted,
                )
        if remaining:
            log.info("sentinel_parcels_without_clear_view", count=len(remaining))
        return readings
