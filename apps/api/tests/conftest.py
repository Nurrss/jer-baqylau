"""Test fixtures.

Tests run against a dedicated ``<db>_test`` database on the same PostGIS server as
``DATABASE_URL`` (the local docker container by default, a service container in CI).
The schema is migrated and seeded once per session; every test runs inside a
transaction that is rolled back, so tests are isolated and fast.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# Configure the app for tests before anything imports settings.
_BASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL", "postgresql://jer:jer@localhost:54322/jer"
)
if not os.environ.get("TEST_DATABASE_URL") and not any(h in _BASE_URL for h in ("@localhost", "@127.0.0.1", "@db:")):
    # Tests drop and recreate a database: never do that against a remote server by accident.
    raise RuntimeError("Tests run only against a local PostGIS; set TEST_DATABASE_URL to override explicitly.")
_base, _, _dbname = _BASE_URL.rpartition("/")
_dbname = _dbname.split("?")[0]
TEST_DB = _dbname if _dbname.endswith("_test") else f"{_dbname}_test"
os.environ.update(
    {
        "ENV": "test",
        "DATABASE_URL": f"{_base}/{TEST_DB}",
        "AUTH_MODE": "local",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_DIR": str(Path(tempfile.mkdtemp(prefix="jer-test-storage-"))),
        "BOT_MODE": "disabled",
        "TELEGRAM_BOT_TOKEN": "",
        "SCHEDULER_ENABLED": "false",
        "SEED_ON_START": "false",
        "RUN_MIGRATIONS_ON_START": "false",
        "SERVICE_API_KEY": "test-service-key",
        "SIGNALS_PER_HOUR_LIMIT": "5",
        "SEED_PARCELS_SOURCE": "generated",
        "LOG_LEVEL": "WARNING",
    }
)

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.providers.notification import LogNotificationProvider, set_notification_provider  # noqa: E402
from app.providers.storage import get_storage  # noqa: E402

SERVICE_HEADERS = {"X-Service-Key": "test-service-key"}


async def _recreate_database() -> None:
    admin_dsn = _BASE_URL.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()
    conn = await asyncpg.connect(f"{admin_dsn.rpartition('/')[0]}/{TEST_DB}")
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    await _recreate_database()
    from app.db.migrate import upgrade_to_head
    from app.seed.loader import seed

    await upgrade_to_head()
    async with db_session.session_scope() as session:
        await seed(session, get_storage())
    yield
    await db_session.dispose_engine()


@pytest.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    async with db_session.get_engine().connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


@pytest.fixture
async def session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """Session whose commits only release a SAVEPOINT; the outer transaction is rolled back."""
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, autoflush=False, join_transaction_mode="create_savepoint"
    )
    async with maker() as s:
        yield s


@pytest.fixture
def notifications() -> LogNotificationProvider:
    provider = LogNotificationProvider()
    set_notification_provider(provider)
    return provider


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    async def _override_db() -> AsyncIterator[AsyncSession]:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.demo_inspector_email,
            "password": settings.demo_inspector_password.get_secret_value(),
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
