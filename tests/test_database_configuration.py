"""Database configuration and schema metadata tests."""

import pytest
from advisor_api.config import Settings
from pydantic import SecretStr, ValidationError

from database.models import SCHEMA, Base


def test_production_rejects_in_memory_persistence() -> None:
    with pytest.raises(ValidationError, match="Production cannot use"):
        Settings(app_env="production", database_mode="memory")


def test_url_mode_requires_asyncpg_url() -> None:
    settings = Settings(
        app_env="test",
        database_mode="url",
        database_url=SecretStr("postgresql+asyncpg://user:secret@localhost/advisor"),
    )

    assert settings.database_url is not None
    assert "secret" not in repr(settings.database_url)


def test_url_mode_rejects_sync_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(
            app_env="test",
            database_mode="url",
            database_url=SecretStr("postgresql+psycopg://user:secret@localhost/advisor"),
        )


def test_cloud_sql_mode_requires_connection_identity() -> None:
    with pytest.raises(ValidationError, match="Missing Cloud SQL settings"):
        Settings(app_env="staging", database_mode="cloud_sql")


def test_cloud_sql_iam_mode_rejects_password() -> None:
    with pytest.raises(ValidationError, match="DB_PASSWORD must be unset"):
        Settings(
            app_env="staging",
            database_mode="cloud_sql",
            instance_connection_name="project:region:instance",
            db_user="advisor-api@project.iam",
            db_name="advisor",
            db_password=SecretStr("do-not-use"),
        )


def test_authoritative_tables_use_dedicated_schema() -> None:
    expected = {
        "advisor.catalog_candidates",
        "advisor.catalog_evidence",
        "advisor.care_plan_previews",
        "advisor.care_plans",
        "advisor.care_tasks",
    }

    assert {f"{table.schema}.{table.name}" for table in Base.metadata.tables.values()} == expected
    assert all(table.schema == SCHEMA for table in Base.metadata.tables.values())
