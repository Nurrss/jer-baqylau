"""Seed the database with demo data if it is empty.

uv run --project apps/api python scripts/seed.py
"""

from __future__ import annotations

import asyncio

import _bootstrap  # noqa: F401


async def main() -> None:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, session_scope
    from app.providers.storage import get_storage
    from app.seed.loader import seed_if_empty

    configure_logging(get_settings().log_level)
    async with session_scope() as session:
        result = await seed_if_empty(session, get_storage())
    await dispose_engine()
    print(f"Seeded: {result.model_dump()}" if result else "Database already has data — nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
