"""Background jobs (APScheduler): periodic satellite scan."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.providers.satellite import get_satellite_provider
from app.services import satellite

log = get_logger(__name__)

SATELLITE_LOCK_ID = 724002


async def satellite_scan_job() -> None:
    async with session_scope() as session:
        # Only one replica runs the scan at a time.
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": SATELLITE_LOCK_ID}
        )
        if not locked:
            log.info("satellite_scan_skipped_locked")
            return
        await satellite.run_scan(session, get_satellite_provider())


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        satellite_scan_job,
        "interval",
        minutes=settings.satellite_scan_interval_minutes,
        id="satellite_scan",
        next_run_time=datetime.now(UTC) + timedelta(minutes=1),
        max_instances=1,
        coalesce=True,
    )
    return scheduler
