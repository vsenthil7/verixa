"""Alembic environment for Verixa migrations.

Wires the SQLAlchemy MetaData from `verixa_runtime.db.metadata` to Alembic
so autogenerate works. Supports both online (live DB) and offline (SQL
script generation) migration modes.

Database URL resolution order:
  1. `DATABASE_URL` environment variable (used in CI / docker-compose)
  2. `sqlalchemy.url` from alembic.ini (local dev default)
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the canonical MetaData object — every schema model file is
# imported here so its tables register against this MetaData.
from verixa_runtime.db import metadata  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the URL from env if present
env_url = os.environ.get("DATABASE_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = metadata


def run_migrations_offline() -> None:
    """Generate SQL scripts without connecting to a DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live DB connection."""
    # For Alembic env.py we use the sync driver. The runtime app uses asyncpg;
    # Alembic uses a sync postgresql:// URL derived from it.
    url = config.get_main_option("sqlalchemy.url") or ""
    sync_url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    config.set_main_option("sqlalchemy.url", sync_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
