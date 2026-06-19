"""Alembic environment — async edition.

URL is read from ``app.core.config.settings.DATABASE_URL``; nothing is
hardcoded.  Models are imported so autogenerate can diff them against the
live schema.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Pull in application settings and models so autogenerate works.
# ---------------------------------------------------------------------------
from app.core.config import settings  # reads .env / environment variables
from app.db.base import Base
from app.db import models as _models  # noqa: F401 — registers all ORM classes

# Alembic config object (alembic.ini).
config = context.config

# Override sqlalchemy.url with the value from our settings so the ini file
# never contains a literal connection string.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Wire up Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — generate SQL script without a live connection.
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Ensure Postgres ENUM types are included in offline output.
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect and apply migrations.
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations inside a synchronous callback."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
