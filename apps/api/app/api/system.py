"""Routes outside /api/v1: health check and signed local file serving."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.session import get_sessionmaker
from app.providers.storage import LocalStorageProvider, get_storage
from app.schemas.misc import HealthOut

router = APIRouter()


async def _db_ok() -> bool:
    try:
        async with get_sessionmaker()() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=3)
        return True
    except Exception:
        return False


async def _redis_ok() -> bool:
    from redis.asyncio import Redis

    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


@router.get(
    "/health",
    response_model=HealthOut,
    tags=["system"],
    responses={503: {"model": HealthOut, "description": "Database unavailable"}},
)
async def health() -> Response:
    settings = get_settings()
    db_ok, redis_ok = await asyncio.gather(_db_ok(), _redis_ok())
    body = HealthOut(
        status="ok" if db_ok and redis_ok else "degraded",
        version=__version__,
        env=settings.env.value,
        database=db_ok,
        redis=redis_ok,
        bot=settings.bot_mode.value if settings.bot_enabled else "disabled",
        storage=get_storage().name,
    )
    # Only the database is critical for serving the panel; Redis affects the bot FSM.
    return JSONResponse(body.model_dump(), status_code=200 if db_ok else 503)


@router.get("/files/{path:path}", include_in_schema=False)
async def local_file(path: str, exp: int = Query(...), sig: str = Query(...)) -> FileResponse:
    storage = get_storage()
    if not isinstance(storage, LocalStorageProvider):
        raise NotFoundError("Not found")
    target = storage.verify(path, exp, sig)
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
