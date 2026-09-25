"""Bot lifecycle inside the API process: polling (local) or webhook (production).

Webhook updates are acknowledged immediately and processed in a background task;
a DB table of processed ``update_id`` makes redelivered updates harmless.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Update
from fastapi import APIRouter, FastAPI, Header, Request, Response
from sqlalchemy.dialects.postgresql import insert

from app.bot.common import FsmTimeoutMiddleware, LanguageMiddleware
from app.bot.handlers import general, knowledge, my, report, status
from app.core.config import BotMode, Settings, get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models import ProcessedUpdate
from app.db.session import session_scope
from app.domain.enums import Lang
from app.providers.notification import (
    LogNotificationProvider,
    TelegramNotificationProvider,
    set_notification_provider,
)

log = get_logger(__name__)

FSM_TTL_SECONDS = 24 * 3600
WEBHOOK_PATH = "/tg/webhook"


class _Runtime:
    bot: Bot | None = None
    dispatcher: Dispatcher | None = None
    storage: BaseStorage | None = None
    polling_task: asyncio.Task[Any] | None = None
    tasks: set[asyncio.Task[Any]] = set()  # noqa: RUF012


runtime = _Runtime()


async def build_storage(settings: Settings) -> BaseStorage:
    try:
        from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

        storage = RedisStorage.from_url(
            settings.redis_url,
            key_builder=DefaultKeyBuilder(prefix="jer:fsm"),
            state_ttl=FSM_TTL_SECONDS,
            data_ttl=FSM_TTL_SECONDS,
        )
        await storage.redis.ping()
        return storage
    except Exception as exc:
        log.warning("fsm_redis_unavailable_using_memory", error=str(exc))
        return MemoryStorage()


def build_dispatcher(storage: BaseStorage) -> Dispatcher:
    dp = Dispatcher(storage=storage)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(LanguageMiddleware())
        observer.outer_middleware(FsmTimeoutMiddleware())
    # Order matters: global cancel/start first, the catch-all fallback last.
    dp.include_routers(
        general.router, status.router, knowledge.router, my.router, report.router, general.fallback_router
    )
    return dp


async def start_bot(app: FastAPI, settings: Settings) -> None:
    if not settings.bot_enabled:
        set_notification_provider(LogNotificationProvider())
        log.info("bot_disabled")
        return
    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    storage = await build_storage(settings)
    dp = build_dispatcher(storage)
    runtime.bot, runtime.dispatcher, runtime.storage = bot, dp, storage
    set_notification_provider(TelegramNotificationProvider(bot))

    try:
        for lang in Lang:
            await bot.set_my_commands(
                [BotCommand(command="start", description=t(lang, "main-menu-hint").rstrip(" 👇"))],
                language_code=lang.value,
            )
    except Exception as exc:
        log.warning("bot_set_commands_failed", error=str(exc))

    if settings.bot_mode is BotMode.POLLING:
        await bot.delete_webhook(drop_pending_updates=False)
        runtime.polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False, allowed_updates=dp.resolve_used_update_types())
        )
        log.info("bot_started", mode="polling")
    else:
        url = f"{settings.public_api_url.rstrip('/')}{WEBHOOK_PATH}"
        await bot.set_webhook(
            url,
            secret_token=settings.telegram_webhook_secret.get_secret_value(),
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        log.info("bot_started", mode="webhook", url=url)


async def stop_bot() -> None:
    if runtime.dispatcher is not None and runtime.polling_task is not None:
        with contextlib.suppress(RuntimeError):  # polling already stopped
            await runtime.dispatcher.stop_polling()
        runtime.polling_task.cancel()
    if runtime.tasks:
        await asyncio.wait(set(runtime.tasks), timeout=10)
    if runtime.bot is not None:
        await runtime.bot.session.close()
    if runtime.storage is not None:
        await runtime.storage.close()
    runtime.bot = runtime.dispatcher = runtime.storage = runtime.polling_task = None


async def _claim_update(update_id: int) -> bool:
    """True if this update was not processed before (idempotency across redeliveries/replicas)."""
    async with session_scope() as session:
        result = await session.execute(
            insert(ProcessedUpdate)
            .values(update_id=update_id)
            .on_conflict_do_nothing()
            .returning(ProcessedUpdate.update_id)
        )
        return result.scalar() is not None


async def process_update(bot: Bot, dp: Dispatcher, update: Update) -> None:
    try:
        if not await _claim_update(update.update_id):
            log.info("tg_update_duplicate_skipped", update_id=update.update_id)
            return
        await dp.feed_update(bot, update)
    except Exception:
        log.exception("tg_update_failed", update_id=update.update_id)


webhook_router = APIRouter()


@webhook_router.post(WEBHOOK_PATH, include_in_schema=False)
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)
) -> Response:
    settings = get_settings()
    bot, dp = runtime.bot, runtime.dispatcher
    if settings.bot_mode is not BotMode.WEBHOOK or bot is None or dp is None:
        raise NotFoundError("Webhook is not enabled")
    expected = settings.telegram_webhook_secret.get_secret_value()
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise ForbiddenError("Invalid webhook secret")
    update = Update.model_validate(await request.json(), context={"bot": bot})
    # Answer Telegram right away; heavy work (DB, geocoding, downloads) runs in the background.
    task = asyncio.create_task(process_update(bot, dp, update))
    runtime.tasks.add(task)
    task.add_done_callback(runtime.tasks.discard)
    return Response(status_code=200)
