"""Sentinel-2 NDVI maths (offline): clear-pixel masking, BOA offset sanity check, clustering."""

from __future__ import annotations

import numpy as np
import pytest

from app.domain.enums import ParcelPurpose, ParcelStatus
from app.providers.satellite import MockSentinelProvider, ParcelSnapshot
from app.providers.sentinel import cluster_bounds, effective_offset, parcel_ndvi_stats


def _mask(shape: tuple[int, int], rows: slice, cols: slice) -> np.ndarray:
    m = np.zeros(shape, dtype=bool)
    m[rows, cols] = True
    return m


def test_ndvi_uses_only_clear_pixels_inside_the_parcel() -> None:
    red = np.full((4, 4), 500, dtype=np.uint16)
    nir = np.full((4, 4), 3000, dtype=np.uint16)
    scl = np.full((4, 4), 4, dtype=np.uint8)  # vegetation
    scl[0, :] = 9  # a cloud row
    red[0, :], nir[0, :] = 9000, 9000  # bright clouds would ruin the mean
    stats = parcel_ndvi_stats(
        red, nir, scl, {"p": _mask((4, 4), slice(0, 4), slice(0, 4))}, scale=0.0001, offset=0
    )
    assert stats["p"].ndvi == pytest.approx((0.3 - 0.05) / (0.3 + 0.05), abs=1e-3)
    assert stats["p"].valid_fraction == pytest.approx(0.75)


def test_fully_clouded_parcel_has_no_valid_pixels() -> None:
    red = np.full((2, 2), 800, dtype=np.uint16)
    scl = np.full((2, 2), 8, dtype=np.uint8)  # cloud medium probability
    stats = parcel_ndvi_stats(red, red, scl, {"p": np.ones((2, 2), dtype=bool)})
    assert stats["p"].valid_fraction == 0


def test_declared_offset_is_ignored_when_it_would_make_reflectance_negative() -> None:
    scl = np.full(100, 4, dtype=np.uint8)
    harmonized_vegetation = np.full(100, 500, dtype=np.uint16)  # 0.05 reflectance without offset
    assert effective_offset(harmonized_vegetation, scl, 0.0001, -0.1) == 0.0
    raw_with_offset = np.full(100, 1500, dtype=np.uint16)  # 0.05 reflectance with offset
    assert effective_offset(raw_with_offset, scl, 0.0001, -0.1) == -0.1


def test_parcels_are_clustered_into_compact_windows() -> None:
    def square(x: float, y: float) -> dict:
        return {
            "type": "Polygon",
            "coordinates": [[[x, y], [x + 30, y], [x + 30, y + 30], [x, y + 30], [x, y]]],
        }

    geoms = {"a": square(100, 100), "b": square(200, 150), "far": square(50_000, 50_000)}
    clusters = cluster_bounds(geoms)
    assert sorted(sorted(ids) for ids, _ in clusters) == [["a", "b"], ["far"]]
    _ids, (minx, miny, maxx, maxy) = next(c for c in clusters if "a" in c[0])
    assert minx < 100
    assert maxx > 230
    assert maxy - miny < 200


async def test_mock_provider_reports_observation_time() -> None:
    parcel = ParcelSnapshot("1", "06:097:904:001", ParcelPurpose.AGRICULTURE, ParcelStatus.OK, None)
    [reading] = await MockSentinelProvider().ndvi([parcel])
    assert reading.observed_at is not None
    assert -0.1 <= reading.ndvi <= 0.95
