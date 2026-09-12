"""Alembic environment for the advisor PostgreSQL schema."""

import asyncio
import os
from logging.config import fileConfig

from advisor_api.config import Settings
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from database.models import SCHEMA, Base
from database.runtime import create_database_runtime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def migration_url() -> str:
    value = os.environ.get("MIGRATION_DATABASE_URL")
    if not value:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for Alembic commands")
    if not value.startswith("postgresql+psycopg://"):
        raise RuntimeError("MIGRATION_DATABASE_URL must use postgresql+psycopg")
    return value


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        context.run_migrations()


def _run_url_migrations() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = migration_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-csearch_path=public"},
    )
    with connectable.connect() as connection:
        _run_with_connection(connection)


async def _run_cloud_sql_migrations() -> None:
    settings = Settings()
    if settings.database_mode != "cloud_sql":
        raise RuntimeError("MIGRATION_DATABASE_URL is required unless DATABASE_MODE=cloud_sql")
    runtime = await create_database_runtime(settings)
    try:
        async with runtime.engine.connect() as connection:
            await connection.run_sync(_run_with_connection)
    finally:
        await runtime.close()


def run_migrations_online() -> None:
    if os.environ.get("MIGRATION_DATABASE_URL"):
        _run_url_migrations()
        return
    asyncio.run(_run_cloud_sql_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
