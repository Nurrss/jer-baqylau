"""Dashboard statistics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Parcel, Signal, StatusTransition
from app.domain.enums import EntityType, ParcelStatus, SignalStatus
from app.domain.state_machine import ACTIVE_VIOLATION_STATUSES
from app.schemas.misc import (
    DashboardStats,
    DayCount,
    Kpi,
    StatusCount,
    UpcomingDeadline,
    ViolationTypeCount,
)
from app.services.parcels import overdue_clause

SIGNALS_CHART_DAYS = 14


async def dashboard(session: AsyncSession) -> DashboardStats:
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    parcels_total, area_total = (
        await session.execute(select(func.count(Parcel.id), func.coalesce(func.sum(Parcel.area_ha), 0)))
    ).one()
    status_counts: dict[ParcelStatus, int] = dict(
        (await session.execute(select(Parcel.status, func.count()).group_by(Parcel.status))).tuples().all()
    )
    overdue = await session.scalar(select(func.count(Parcel.id)).where(overdue_clause(now)))
    signals_7d = await session.scalar(select(func.count(Signal.id)).where(Signal.created_at >= week_ago))
    signals_new = await session.scalar(select(func.count(Signal.id)).where(Signal.status == SignalStatus.NEW))

    # Reaction time: signal creation → first inspector action on it.
    first_action = (
        select(StatusTransition.entity_id, func.min(StatusTransition.created_at).label("acted_at"))
        .where(StatusTransition.entity_type == EntityType.SIGNAL, StatusTransition.from_status.is_not(None))
        .group_by(StatusTransition.entity_id)
        .subquery()
    )
    avg_seconds = await session.scalar(
        select(func.avg(func.extract("epoch", first_action.c.acted_at - Signal.created_at))).join(
            first_action, first_action.c.entity_id == Signal.id
        )
    )

    day = cast(func.timezone("Asia/Almaty", Signal.created_at), Date)
    start = (now - timedelta(days=SIGNALS_CHART_DAYS - 1)).date()
    per_day: dict[date, int] = dict(
        (await session.execute(select(day, func.count(Signal.id)).where(day >= start).group_by(day)))
        .tuples()
        .all()
    )
    signals_by_day = [
        DayCount(date=d, count=int(per_day.get(d, 0)))
        for d in (start + timedelta(days=i) for i in range(SIGNALS_CHART_DAYS))
    ]

    by_type = (
        await session.execute(
            select(Parcel.violation_type, func.count())
            .where(Parcel.violation_type.is_not(None), Parcel.status.in_(ACTIVE_VIOLATION_STATUSES))
            .group_by(Parcel.violation_type)
            .order_by(func.count().desc())
        )
    ).all()

    deadlines = list(
        await session.scalars(
            select(Parcel)
            .where(Parcel.deadline_at.is_not(None), Parcel.status.in_(ACTIVE_VIOLATION_STATUSES))
            .order_by(Parcel.deadline_at)
            .limit(8)
        )
    )

    return DashboardStats(
        kpi=Kpi(
            parcels_total=int(parcels_total),
            area_total_ha=round(float(area_total), 2),
            violations_active=int(status_counts.get(ParcelStatus.VIOLATION, 0))
            + int(status_counts.get(ParcelStatus.IN_REMEDIATION, 0)),
            in_remediation=int(status_counts.get(ParcelStatus.IN_REMEDIATION, 0)),
            overdue=int(overdue or 0),
            signals_7d=int(signals_7d or 0),
            signals_new=int(signals_new or 0),
            avg_reaction_hours=round(float(avg_seconds) / 3600, 1) if avg_seconds is not None else None,
        ),
        signals_by_day=signals_by_day,
        violations_by_type=[ViolationTypeCount(violation_type=vt, count=int(c)) for vt, c in by_type],
        status_counts=[StatusCount(status=s, count=int(status_counts.get(s, 0))) for s in ParcelStatus],
        upcoming_deadlines=[
            UpcomingDeadline(
                parcel_id=str(p.id),
                cadastral_number=p.cadastral_number,
                status=p.status,
                violation_type=p.violation_type,
                deadline_at=p.deadline_at,
                days_left=_days_between(now.date(), p.deadline_at.date()),  # type: ignore[union-attr]
            )
            for p in deadlines
        ],
    )


def _days_between(today: date, deadline: date) -> int:
    return (deadline - today).days
