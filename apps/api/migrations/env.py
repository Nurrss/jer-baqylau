"""Alembic environment (async, PostGIS-aware)."""

from __future__ import annotations

import asyncio

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.db.models import Base
from app.db.session import build_engine

target_metadata = Base.metadata

# Tables owned by PostGIS / Supabase, never managed by our migrations.
EXTERNAL_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns", "raster_columns"}


def include_name(name, type_, parent_names):  # type: ignore[no-untyped-def]
    # Only the default (public) schema; PostGIS images ship tiger/topology schemas.
    if type_ == "schema":
        return name in (None, "public")
    return True


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    if type_ == "table" and (name in EXTERNAL_TABLES or (reflected and compare_to is None)):
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


def _configure(connection: Connection | None = None, **kwargs: object) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        include_name=include_name,
        include_schemas=False,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
        compare_type=True,
        **kwargs,  # type: ignore[arg-type]
    )


def run_migrations_offline() -> None:
    _configure(url=get_settings().async_database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = build_engine(get_settings())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
