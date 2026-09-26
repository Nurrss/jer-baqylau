"""Cross-check a parcel against other state data: cadastre registry and declared sowing vs satellite."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NdviScan, Parcel
from app.providers.cadastre import get_cadastre_provider
from app.providers.registry import get_subsidy_registry
from app.schemas.common import ApiModel

# Peak season NDVI below this on a field declared as sown = no crop was grown.
SOWN_FIELD_MIN_PEAK = 0.35
GROWING_MONTHS = range(5, 9)


class CrossCheckItem(ApiModel):
    source: Literal["GBD_ZKS", "SUBSIDIES"]
    status: Literal["ok", "mismatch", "info"]
    code: str
    params: dict[str, Any]
    is_demo: bool


class CrossCheck(ApiModel):
    items: list[CrossCheckItem]
    mismatches: int


async def season_peak(session: AsyncSession, parcel_id: Any, year: int) -> tuple[float | None, int]:
    """Max NDVI in May–August of ``year`` from real scans/history, and how many observations it is based on."""
    row = (
        await session.execute(
            select(func.max(NdviScan.ndvi), func.count(NdviScan.id)).where(
                NdviScan.parcel_id == parcel_id,
                NdviScan.observed_at.is_not(None),
                func.extract("year", NdviScan.observed_at) == year,
                func.extract("month", NdviScan.observed_at).in_(list(GROWING_MONTHS)),
            )
        )
    ).one()
    return (float(row[0]) if row[0] is not None else None), int(row[1])


async def subsidy_check(session: AsyncSession, parcel: Parcel, year: int) -> CrossCheckItem | None:
    registry = get_subsidy_registry()
    declarations = await registry.declarations(
        parcel.cadastral_number, parcel.purpose, float(parcel.area_ha), year
    )
    if not declarations:
        return None
    decl = declarations[0]
    peak, observations = await season_peak(session, parcel.id, year)
    params: dict[str, Any] = {
        "year": decl.year,
        "crop": decl.crop,
        "area_ha": decl.area_ha,
        "subsidy_kzt": decl.subsidy_kzt,
    }
    if peak is None:
        # No growing-season satellite data yet: fall back to the latest value (weaker evidence).
        peak = float(parcel.ndvi) if parcel.ndvi is not None else None
        params["basis"] = "latest"
    else:
        params["basis"] = "season"
        params["observations"] = observations
    if peak is None:
        return CrossCheckItem(
            source="SUBSIDIES",
            status="info",
            code="SUBSIDY_NO_SATELLITE",
            params=params,
            is_demo=registry.is_demo,
        )
    params["peak_ndvi"] = round(peak, 2)
    status: Literal["ok", "mismatch"] = "mismatch" if peak < SOWN_FIELD_MIN_PEAK else "ok"
    code = "SUBSIDY_NO_CROP" if status == "mismatch" else "SUBSIDY_CROP_CONFIRMED"
    return CrossCheckItem(
        source="SUBSIDIES", status=status, code=code, params=params, is_demo=registry.is_demo
    )


async def crosscheck(session: AsyncSession, parcel: Parcel) -> CrossCheck:
    items: list[CrossCheckItem] = []
    provider = get_cadastre_provider()
    record = await provider.get(session, parcel.cadastral_number)
    if record is not None:
        items.append(
            CrossCheckItem(
                source="GBD_ZKS",
                status="ok" if record.matches_local else "mismatch",
                code="CADASTRE_MATCH" if record.matches_local else "CADASTRE_AREA_MISMATCH",
                params={"registry_area_ha": record.area_ha, "local_area_ha": float(parcel.area_ha)},
                is_demo=True,
            )
        )
    subsidy = await subsidy_check(session, parcel, datetime.now(UTC).year)
    if subsidy is not None:
        items.append(subsidy)
    return CrossCheck(items=items, mismatches=sum(1 for i in items if i.status == "mismatch"))
