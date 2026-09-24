"""Bot lifecycle inside the API process. Full dispatcher wiring lands in Phase 3."""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import Settings
from app.core.logging import get_logger
from app.providers.notification import LogNotificationProvider, set_notification_provider

log = get_logger(__name__)


async def start_bot(app: FastAPI, settings: Settings) -> None:
    set_notification_provider(LogNotificationProvider())
    log.info("bot_disabled")


async def stop_bot() -> None:
    return None
