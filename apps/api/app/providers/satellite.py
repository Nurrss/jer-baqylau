"""Satellite monitoring adapters.

``MockSentinelProvider`` imitates a Sentinel-2 NDVI pipeline: it returns a stable,
plausible NDVI per parcel so the demo layer is meaningful. A real implementation
(Sentinel Hub Statistical API / Copernicus Data Space openEO) plugs in via the same
``SatelliteProvider`` protocol — see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.domain.enums import ParcelPurpose, ParcelStatus, ViolationType

# NDVI below this value on land that should be cultivated/built → "probably unused" candidate.
UNUSED_NDVI_THRESHOLD = 0.2


@dataclass(frozen=True, slots=True)
class ParcelSnapshot:
    id: str
    cadastral_number: str
    purpose: ParcelPurpose
    status: ParcelStatus
    violation_type: ViolationType | None
    geometry: dict[str, Any] | None = None  # GeoJSON, EPSG:4326


@dataclass(frozen=True, slots=True)
class NdviReading:
    parcel_id: str
    ndvi: float
    flagged: bool
    observed_at: datetime | None = None  # acquisition time of the scene
    scene_id: str | None = None
    valid_fraction: float | None = None  # share of cloud-free pixels inside the parcel


class SatelliteProvider(Protocol):
    name: str
    is_demo: bool
    threshold: float

    async def ndvi(self, parcels: list[ParcelSnapshot], at: datetime | None = None) -> list[NdviReading]: ...


def _unit(seed: str) -> float:
    """Deterministic pseudo-random number in [0, 1) from a string."""
    return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big") / 2**64


class MockSentinelProvider:
    name = "mock-sentinel-2"
    is_demo = True
    threshold = UNUSED_NDVI_THRESHOLD

    async def ndvi(self, parcels: list[ParcelSnapshot], at: datetime | None = None) -> list[NdviReading]:
        moment = at or datetime.now(UTC)
        # Mild seasonality: greener in May–August.
        season = {5: 0.08, 6: 0.12, 7: 0.1, 8: 0.05, 11: -0.05, 12: -0.08, 1: -0.1, 2: -0.08}.get(
            moment.month, 0.0
        )
        day_noise_seed = moment.strftime("%Y-%m-%d")
        readings: list[NdviReading] = []
        for parcel in parcels:
            base = _unit(parcel.cadastral_number)
            if parcel.violation_type is ViolationType.UNUSED:
                value = 0.06 + base * 0.1
            elif parcel.purpose is ParcelPurpose.AGRICULTURE:
                # ~25% of agricultural land looks fallow → candidates for inspection.
                value = 0.1 + base * 0.12 if base < 0.25 else 0.45 + base * 0.35
            elif parcel.purpose in (ParcelPurpose.IZHS, ParcelPurpose.LPH):
                value = 0.25 + base * 0.35
            else:
                value = 0.18 + base * 0.2
            value += season + (_unit(parcel.id + day_noise_seed) - 0.5) * 0.04
            value = round(min(max(value, -0.1), 0.95), 3)
            flagged = parcel.purpose in (ParcelPurpose.AGRICULTURE, ParcelPurpose.LPH) and (
                value < UNUSED_NDVI_THRESHOLD
            )
            flagged = flagged or parcel.violation_type is ViolationType.UNUSED
            readings.append(
                NdviReading(
                    parcel_id=parcel.id, ndvi=value, flagged=flagged, observed_at=moment, valid_fraction=1.0
                )
            )
        return readings


def get_satellite_provider() -> SatelliteProvider:
    """SATELLITE_PROVIDER=sentinel → real Sentinel-2 L2A (Earth Search); anything else → demo mock."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.satellite_provider == "sentinel":
        from app.providers.sentinel import EarthSearchSentinelProvider

        return EarthSearchSentinelProvider(stac_url=settings.sentinel_stac_url)
    return MockSentinelProvider()
