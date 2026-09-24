"""Apply supabase/*.sql (RLS, realtime publication, storage bucket) in order. Idempotent.

    uv run --project apps/api python scripts/apply_supabase_sql.py
Uses DATABASE_URL from .env; run after migrations (`make migrate`).
"""

from __future__ import annotations

import asyncio
import ssl

import _bootstrap
import asyncpg


async def main() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    dsn = settings.async_database_url.replace("postgresql+asyncpg://", "postgresql://")
    ssl_ctx = None
    if settings.database_requires_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(dsn, ssl=ssl_ctx)
    try:
        for path in sorted((_bootstrap.REPO_ROOT / "supabase").glob("[0-9]*.sql")):
            await conn.execute(path.read_text(encoding="utf-8"))
            print(f"applied {path.name}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
