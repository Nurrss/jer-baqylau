"""Other state registries used for cross-checks (demo adapters).

``MockSubsidyRegistry`` imitates the agricultural subsidy register: which parcels declared sowing
this season (and received per-hectare subsidies). In production it is a client of the subsidy
information system via the government integration bus (ШЭП) with the same interface.
A declared crop on a field where the satellite sees bare soil is the classic subsidy-fraud signal.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app.domain.enums import ParcelPurpose

CROPS = ("wheat", "barley", "sugar_beet", "alfalfa")


@dataclass(frozen=True, slots=True)
class SubsidyDeclaration:
    year: int
    crop: str
    area_ha: float
    subsidy_kzt: int


class SubsidyRegistry(Protocol):
    name: str
    is_demo: bool

    async def declarations(
        self, cadastral_number: str, purpose: ParcelPurpose, area_ha: float, year: int
    ) -> list[SubsidyDeclaration]: ...


class MockSubsidyRegistry:
    name = "mock-subsidy-registry"
    is_demo = True

    async def declarations(
        self, cadastral_number: str, purpose: ParcelPurpose, area_ha: float, year: int
    ) -> list[SubsidyDeclaration]:
        if purpose is not ParcelPurpose.AGRICULTURE:
            return []
        seed = int(hashlib.sha256(f"{cadastral_number}:{year}".encode()).hexdigest()[:8], 16)
        if seed % 10 >= 7:  # ~70 % of fields declare sowing
            return []
        crop = CROPS[seed % len(CROPS)]
        per_ha = (8_000, 10_000, 25_000, 12_000)[seed % len(CROPS)]
        declared = round(area_ha * (0.85 + (seed % 15) / 100), 2)
        return [
            SubsidyDeclaration(year=year, crop=crop, area_ha=declared, subsidy_kzt=int(declared * per_ha))
        ]


def get_subsidy_registry() -> SubsidyRegistry:
    return MockSubsidyRegistry()
