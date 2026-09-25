"""Reset demo data to the initial state.

Local database (DATABASE_URL from .env):
    uv run --project apps/api python scripts/demo_reset.py

Deployed API (uses SERVICE_API_KEY from .env or --service-key):
    uv run --project apps/api python scripts/demo_reset.py --base-url https://<api-host>
"""

from __future__ import annotations

import argparse
import asyncio
import os

import _bootstrap  # noqa: F401


async def reset_local() -> None:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.db.session import dispose_engine, session_scope
    from app.providers.storage import get_storage
    from app.seed.loader import reset

    configure_logging(get_settings().log_level)
    from app.services import outbox

    async with session_scope() as session:
        result = await reset(session, get_storage())
    await outbox.drain()  # old photo files are removed after commit
    await dispose_engine()
    print(f"Demo reset done: {result.model_dump()}")


def reset_remote(base_url: str, service_key: str) -> None:
    import httpx

    resp = httpx.post(
        f"{base_url.rstrip('/')}/api/v1/dev/demo-reset", headers={"X-Service-Key": service_key}, timeout=300
    )
    resp.raise_for_status()
    print(f"Demo reset done on {base_url}: {resp.json()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", help="Reset through a deployed API instead of the local database")
    parser.add_argument("--service-key", default=None)
    args = parser.parse_args()
    if args.base_url:
        from app.core.config import get_settings

        key = (
            args.service_key
            or os.getenv("SERVICE_API_KEY")
            or get_settings().service_api_key.get_secret_value()
        )
        reset_remote(args.base_url, key)
    else:
        asyncio.run(reset_local())


if __name__ == "__main__":
    main()
