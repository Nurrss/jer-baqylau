"""Programmatic Alembic upgrade (used on container start)."""

from __future__ import annotations

import asyncio

from alembic import command
from alembic.config import Config

from app.core.config import API_ROOT


def _upgrade() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "head")


async def upgrade_to_head() -> None:
    # env.py runs its own event loop, so execute it in a worker thread.
    await asyncio.to_thread(_upgrade)
