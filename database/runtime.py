"""Async SQLAlchemy runtime for URL-based PostgreSQL and Google Cloud SQL."""

import asyncio
from dataclasses import dataclass
from typing import Any

from advisor_api.config import Settings
from google.cloud.sql.connector import Connector, IPTypes
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

type AsyncSessionFactory = async_sessionmaker[AsyncSession]
REQUIRED_SCHEMA_CAPABILITIES = frozenset(
    {
        "catalog_candidates.candidate_id",
        "catalog_candidates.category",
        "catalog_candidates.features",
        "catalog_candidates.active",
        "catalog_evidence.candidate_id",
        "catalog_evidence.source_url",
        "catalog_evidence.reviewed_at",
        "knowledge_sources.source_id",
        "knowledge_sources.status",
        "knowledge_chunks.chunk_id",
        "knowledge_chunks.namespace",
        "knowledge_chunks.indexed_at",
        "plant_toxicity.toxicity_id",
        "plant_toxicity.normalized_scientific_name",
        "plant_toxicity.animal_species",
        "plant_toxicity.toxicity_status",
        "plant_toxicity.active",
        "care_plan_previews.preview_id",
        "care_plan_previews.expires_at",
        "care_plan_previews.consumed_at",
        "care_plans.plan_id",
        "care_plans.owner_id",
        "care_plans.status",
        "care_plans.version",
        "care_tasks.task_id",
        "care_tasks.plan_id",
        "care_tasks.completed_at",
    }
)


@dataclass(slots=True)
class DatabaseRuntime:
    engine: AsyncEngine
    session_factory: AsyncSessionFactory
    connector: Connector | None = None

    async def verify(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            revision = await connection.scalar(
                text("SELECT version_num FROM advisor.alembic_version")
            )
            capabilities = set(
                await connection.scalars(
                    text(
                        """
                        SELECT table_name || '.' || column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'advisor'
                        """
                    )
                )
            )
        if not revision:
            raise RuntimeError("Database does not have an Alembic schema revision")
        missing = REQUIRED_SCHEMA_CAPABILITIES - capabilities
        if missing:
            raise RuntimeError(
                "Database schema is incompatible; missing capabilities: "
                + ", ".join(sorted(missing))
            )

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()
        if self.connector is not None:
            await self.connector.close_async()


async def create_database_runtime(settings: Settings) -> DatabaseRuntime:
    if settings.database_mode == "memory":
        raise ValueError("A database runtime cannot be created in memory mode")

    engine_options: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        "pool_recycle": settings.db_pool_recycle_seconds,
    }

    connector: Connector | None = None
    if settings.database_mode == "url":
        if settings.database_url is None:  # validated by Settings; defensive for type narrowing
            raise ValueError("DATABASE_URL is required")
        url = settings.database_url.get_secret_value()
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg dialect")
        engine = create_async_engine(url, **engine_options)
    else:
        if not settings.instance_connection_name or not settings.db_user or not settings.db_name:
            raise ValueError("Cloud SQL settings are incomplete")
        instance_connection_name = settings.instance_connection_name
        db_user = settings.db_user
        db_name = settings.db_name
        ip_type = {
            "PRIVATE": IPTypes.PRIVATE,
            "PUBLIC": IPTypes.PUBLIC,
            "PSC": IPTypes.PSC,
        }[settings.cloud_sql_ip_type]
        connector = Connector(
            loop=asyncio.get_running_loop(),
            ip_type=ip_type,
            enable_iam_auth=settings.cloud_sql_enable_iam_auth,
            refresh_strategy="LAZY",
        )

        async def connect() -> Any:
            arguments: dict[str, object] = {
                "user": db_user,
                "db": db_name,
                "enable_iam_auth": settings.cloud_sql_enable_iam_auth,
            }
            if settings.db_password is not None:
                arguments["password"] = settings.db_password.get_secret_value()
            connection = await connector.connect_async(
                instance_connection_name,
                "asyncpg",
                **arguments,
            )
            return connection

        engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=connect,
            **engine_options,
        )

    return DatabaseRuntime(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        connector=connector,
    )
