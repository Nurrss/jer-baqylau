"""Cadastre registry adapters.

``LocalDbProvider`` reads our own PostGIS copy. ``MockGbdZksProvider`` imitates the
state land cadastre database (ГБД ЗКС / egov API): it returns a registry-style record
so the panel can show a "reconcile with the registry" block. A real client would call
the government integration bus (ШЭП) with the same interface — see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Parcel
from app.domain.enums import OwnerType, ParcelPurpose

PURPOSE_REGISTRY_NAMES: dict[ParcelPurpose, str] = {
    ParcelPurpose.IZHS: "Для индивидуального жилищного строительства",
    ParcelPurpose.AGRICULTURE: "Для ведения сельскохозяйственного производства",
    ParcelPurpose.COMMERCIAL: "Для коммерческой деятельности",
    ParcelPurpose.INDUSTRIAL: "Для размещения промышленных объектов",
    ParcelPurpose.LPH: "Для ведения личного подсобного хозяйства",
}

RIGHT_TYPES: dict[OwnerType, str] = {
    OwnerType.PRIVATE: "Частная собственность",
    OwnerType.LEASE: "Временное возмездное землепользование (аренда)",
    OwnerType.STATE: "Государственная собственность",
}


@dataclass(slots=True)
class CadastreRecordData:
    provider: str
    cadastral_number: str
    purpose: str
    area_ha: float
    right_type: str
    right_holder: str
    registered_at: date | None
    encumbrances: list[str] = field(default_factory=list)
    matches_local: bool = True
    discrepancies: list[str] = field(default_factory=list)


class CadastreProvider(Protocol):
    name: str

    async def get(self, session: AsyncSession, cadastral_number: str) -> CadastreRecordData | None: ...


class LocalDbProvider:
    name = "local-db"

    async def get(self, session: AsyncSession, cadastral_number: str) -> CadastreRecordData | None:
        parcel = await session.scalar(select(Parcel).where(Parcel.cadastral_number == cadastral_number))
        if parcel is None:
            return None
        return CadastreRecordData(
            provider=self.name,
            cadastral_number=parcel.cadastral_number,
            purpose=PURPOSE_REGISTRY_NAMES[parcel.purpose],
            area_ha=float(parcel.area_ha),
            right_type=RIGHT_TYPES[parcel.owner_type],
            right_holder="—",
            registered_at=None,
        )


def _h(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:4], "big")


class MockGbdZksProvider:
    """Deterministic imitation of the ГБД ЗКС registry response."""

    name = "mock-gbd-zks"
    _holders = ("ТОО «Агро-Жамбыл»", "ИП Ерлан С.", "КХ «Береке»", "Айгуль Н.", "ТОО «Тараз Құрылыс»")

    async def get(self, session: AsyncSession, cadastral_number: str) -> CadastreRecordData | None:
        parcel = await session.scalar(select(Parcel).where(Parcel.cadastral_number == cadastral_number))
        if parcel is None:
            return None
        seed = _h(cadastral_number)
        registry_area = float(parcel.area_ha)
        discrepancies: list[str] = []
        # ~15% of records show an area mismatch — typical for self-seizure cases.
        if seed % 100 < 15:
            registry_area = round(registry_area * 0.9, 4)
            discrepancies.append("area")
        encumbrances: list[str] = []
        if seed % 7 == 0:
            encumbrances.append("Охранная зона ЛЭП")
        if seed % 11 == 0:
            encumbrances.append("Сервитут проезда")
        holder = (
            "Акимат Жамбылской области"
            if parcel.owner_type is OwnerType.STATE
            else (self._holders[seed % len(self._holders)])
        )
        return CadastreRecordData(
            provider=self.name,
            cadastral_number=parcel.cadastral_number,
            purpose=PURPOSE_REGISTRY_NAMES[parcel.purpose],
            area_ha=registry_area,
            right_type=RIGHT_TYPES[parcel.owner_type],
            right_holder=holder,
            registered_at=date(2008, 1, 1) + timedelta(days=seed % 5800),
            encumbrances=encumbrances,
            matches_local=not discrepancies,
            discrepancies=discrepancies,
        )


def get_cadastre_provider() -> CadastreProvider:
    return MockGbdZksProvider()
