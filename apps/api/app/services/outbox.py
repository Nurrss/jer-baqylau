"""Run side effects (Telegram notifications, file cleanup) only after a successful commit.

Services call :func:`after_commit` with a coroutine factory; the callbacks are
scheduled as background tasks when the surrounding transaction commits and are
dropped on rollback. This keeps "DB changed ⇔ citizen notified" consistent for
both the API and the bot, which share the same services.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.logging import get_logger

log = get_logger(__name__)

Callback = Callable[[], Awaitable[Any]]
_KEY = "after_commit_callbacks"
_background_tasks: set[asyncio.Task[Any]] = set()


def after_commit(session: AsyncSession, callback: Callback) -> None:
    session.sync_session.info.setdefault(_KEY, []).append(callback)


async def _run(callback: Callback) -> None:
    try:
        await callback()
    except Exception:
        log.exception("after_commit_callback_failed")


@event.listens_for(Session, "after_commit")
def _on_commit(session: Session) -> None:
    callbacks: list[Callback] = session.info.pop(_KEY, [])
    if not callbacks:
        return
    loop = asyncio.get_running_loop()
    for callback in callbacks:
        task = loop.create_task(_run(callback))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)


@event.listens_for(Session, "after_rollback")
def _on_rollback(session: Session) -> None:
    session.info.pop(_KEY, None)


async def drain(max_wait: float = 10.0) -> None:
    """Wait for pending callbacks (graceful shutdown, tests)."""
    if _background_tasks:
        await asyncio.wait(set(_background_tasks), timeout=max_wait)
