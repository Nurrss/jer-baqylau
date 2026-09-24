"""FastAPI application: REST API + Telegram bot + scheduler in one process."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app import __version__
from app.api.router import api_router
from app.api.system import router as system_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, session_scope
from app.providers.storage import SupabaseStorageProvider, get_storage
from app.services import outbox

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log.info("startup", env=settings.env.value, version=__version__, storage=get_storage().name)

    if settings.run_migrations_on_start:
        from app.db.migrate import upgrade_to_head

        await upgrade_to_head()
        log.info("migrations_applied")

    storage = get_storage()
    if isinstance(storage, SupabaseStorageProvider):
        await storage.ensure_bucket()

    if settings.seed_on_start:
        from app.seed.loader import seed_if_empty

        async with session_scope() as session:
            await seed_if_empty(session, storage)

    scheduler = None
    if settings.scheduler_enabled:
        from app.workers.scheduler import build_scheduler

        scheduler = build_scheduler(settings)
        scheduler.start()

    from app.bot.runtime import start_bot, stop_bot

    await start_bot(app, settings)
    try:
        yield
    finally:
        await stop_bot()
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await outbox.drain()
        await dispose_engine()
        log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ЖерБақылау API",
        version=__version__,
        description=(
            "Цифровой мониторинг земель: панель инспектора, «Народный контроль» и статусы заявлений.\n\n"
            "Ошибки возвращаются в формате `{error: {code, message, details}}`."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Service-Key"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        if request.url.path not in ("/health",):
            log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=elapsed_ms,
                request_id=request_id,
            )
        return response

    register_error_handlers(app)
    app.include_router(system_router)
    app.include_router(api_router)
    return app


app = create_app()
