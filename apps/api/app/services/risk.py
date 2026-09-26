"""Risk score of parcels and the inspection plan (risk-based + reproducible random sample).

Who gets inspected is decided by the system, not by an individual inspector:
* most of the plan is the highest-risk parcels (with the reasons shown);
* a share is a random control sample. Its seed is ``sha256(date + audit chain head)`` — it cannot be
  tailored in advance (the chain head depends on every past action) and anyone can reproduce it later.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InspectionRequest, NdviScan, Parcel, Signal, StatusTransition
from app.domain.enums import (
    EntityType,
    EventType,
    InspectionReason,
    InspectionStatus,
    ParcelStatus,
    SignalStatus,
)
from app.domain.state_machine import ACTIVE_VIOLATION_STATUSES
from app.providers.registry import get_subsidy_registry
from app.services import audit
from app.services.crosscheck import GROWING_MONTHS, SOWN_FIELD_MIN_PEAK
from app.services.inspections import create_request

MAX_SCORE = 100
LEASE_WINDOW = timedelta(days=90)


@dataclass(slots=True)
class RiskFactor:
    code: str
    points: int
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParcelRisk:
    parcel_id: uuid.UUID
    cadastral_number: str
    status: ParcelStatus
    score: int
    factors: list[RiskFactor]
    lon: float
    lat: float


async def compute_risks(session: AsyncSession, now: datetime | None = None) -> list[ParcelRisk]:
    now = now or datetime.now(UTC)
    rows = (
        await session.execute(
            select(Parcel, func.ST_X(Parcel.centroid), func.ST_Y(Parcel.centroid)).where(
                Parcel.status != ParcelStatus.RETURNED_TO_STATE
            )
        )
    ).all()
    open_signals: dict[uuid.UUID | None, int] = dict(
        (
            await session.execute(
                select(Signal.parcel_id, func.count(Signal.id))
                .where(
                    Signal.parcel_id.is_not(None),
                    Signal.status.in_([SignalStatus.NEW, SignalStatus.IN_REVIEW]),
                )
                .group_by(Signal.parcel_id)
            )
        )
        .tuples()
        .all()
    )
    past_violations: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(StatusTransition.entity_id, func.count(StatusTransition.id))
                .where(
                    StatusTransition.entity_type == EntityType.PARCEL,
                    StatusTransition.to_status == ParcelStatus.VIOLATION.value,
                )
                .group_by(StatusTransition.entity_id)
            )
        )
        .tuples()
        .all()
    )

    # Declared sowing (subsidy register) vs this season's satellite peak, for all parcels in one query.
    season_peaks: dict[uuid.UUID, float] = dict(
        (
            await session.execute(
                select(NdviScan.parcel_id, func.max(NdviScan.ndvi))
                .where(
                    NdviScan.observed_at.is_not(None),
                    func.extract("year", NdviScan.observed_at) == now.year,
                    func.extract("month", NdviScan.observed_at).in_(list(GROWING_MONTHS)),
                )
                .group_by(NdviScan.parcel_id)
            )
        )
        .tuples()
        .all()
    )
    registry = get_subsidy_registry()

    risks: list[ParcelRisk] = []
    for parcel, lon, lat in rows:
        factors: list[RiskFactor] = []
        if parcel.ndvi_flagged:
            factors.append(RiskFactor("NDVI_LOW", 30, {"ndvi": round(parcel.ndvi or 0, 2)}))
        if n := open_signals.get(parcel.id, 0):
            factors.append(RiskFactor("OPEN_SIGNALS", min(15 * n, 45), {"count": n}))
        if parcel.deadline_at and parcel.status in ACTIVE_VIOLATION_STATUSES and parcel.deadline_at < now:
            factors.append(RiskFactor("OVERDUE", 30, {"days": (now - parcel.deadline_at).days}))
        if n := past_violations.get(parcel.id, 0):
            factors.append(RiskFactor("REPEAT_VIOLATIONS", min(10 * n, 30), {"count": n}))
        if parcel.lease_until and now.date() <= parcel.lease_until <= (now + LEASE_WINDOW).date():
            factors.append(RiskFactor("LEASE_ENDING", 10, {"days": (parcel.lease_until - now.date()).days}))
        declarations = await registry.declarations(
            parcel.cadastral_number, parcel.purpose, float(parcel.area_ha), now.year
        )
        peak = season_peaks.get(parcel.id, parcel.ndvi)
        if declarations and peak is not None and peak < SOWN_FIELD_MIN_PEAK:
            factors.append(
                RiskFactor(
                    "SUBSIDY_MISMATCH", 25, {"crop": declarations[0].crop, "peak_ndvi": round(peak, 2)}
                )
            )
        score = min(sum(f.points for f in factors), MAX_SCORE)
        risks.append(ParcelRisk(parcel.id, parcel.cadastral_number, parcel.status, score, factors, lon, lat))
    risks.sort(key=lambda r: (-r.score, r.cadastral_number))
    return risks


def sample_seed(day: date, chain_head: str) -> str:
    return hashlib.sha256(f"{day.isoformat()}:{chain_head}".encode()).hexdigest()[:16]


@dataclass(slots=True)
class Plan:
    seed: str
    requests: list[InspectionRequest]


async def create_plan(session: AsyncSession, *, size: int, random_share: float, actor: str) -> Plan:
    now = datetime.now(UTC)
    busy = set(
        await session.scalars(
            select(InspectionRequest.parcel_id).where(
                InspectionRequest.status.in_([InspectionStatus.REQUESTED, InspectionStatus.SUBMITTED])
            )
        )
    )
    risks = [r for r in await compute_risks(session, now) if r.parcel_id not in busy]
    n_random = min(round(size * random_share), size)
    n_risk = size - n_random
    by_risk = [r for r in risks if r.score > 0][:n_risk]

    head, _ = await audit.chain_state(session)
    seed = sample_seed(now.date(), head)
    rest = sorted((r for r in risks if r not in by_risk), key=lambda r: r.cadastral_number)
    by_random = random.Random(seed).sample(rest, k=min(n_random, len(rest)))

    created: list[InspectionRequest] = []
    for risk, reason in [(r, InspectionReason.RISK) for r in by_risk] + [
        (r, InspectionReason.RANDOM) for r in by_random
    ]:
        note = (
            ", ".join(f.code for f in risk.factors) if reason is InspectionReason.RISK else f"random:{seed}"
        )
        created.append(await create_request(session, risk.parcel_id, reason=reason, actor=actor, note=note))
    await audit.emit_event(
        session,
        EventType.INSPECTION_PLAN_CREATED,
        {
            "seed": seed,
            "chain_head": head,
            "risk": [r.cadastral_number for r in by_risk],
            "random": [r.cadastral_number for r in by_random],
            "actor": actor,
        },
    )
    return Plan(seed=seed, requests=created)
