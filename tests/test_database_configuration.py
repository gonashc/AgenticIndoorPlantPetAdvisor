"""Database configuration and schema metadata tests."""

import pytest
from advisor_api.config import Settings
from advisor_api.container import build_configured_container
from pydantic import SecretStr, ValidationError

from database.models import SCHEMA, Base


def test_production_rejects_in_memory_persistence() -> None:
    with pytest.raises(ValidationError, match="Production cannot use"):
        Settings(_env_file=None, app_env="production", database_mode="memory")


def test_production_requires_iap_authentication() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=google_iap"):
        Settings(
            _env_file=None,
            app_env="production",
            database_mode="url",
            database_url=SecretStr("postgresql+asyncpg://user:secret@localhost/advisor"),
        )


def test_iap_authentication_requires_resource_audience() -> None:
    with pytest.raises(ValidationError, match="IAP_AUDIENCE"):
        Settings(_env_file=None, app_env="test", auth_mode="google_iap")


def test_openai_explanations_require_retrieval() -> None:
    with pytest.raises(ValidationError, match="approved Pinecone retrieval"):
        Settings(_env_file=None, explanation_mode="openai")


def test_remote_mcp_requires_https_endpoints() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            _env_file=None,
            mcp_mode="remote",
            mcp_places_url="http://places.example/mcp",
            mcp_adoption_url="https://adoption.example/mcp",
        )


def test_remote_mcp_can_enable_only_the_places_service() -> None:
    settings = Settings(
        _env_file=None,
        mcp_mode="remote",
        mcp_auth_mode="google_cloud_run",
        mcp_places_url="https://places.example/mcp",
        mcp_places_audience="https://places.example",
    )

    assert settings.mcp_adoption_url is None


def test_remote_mcp_can_enable_only_the_adoption_service() -> None:
    settings = Settings(
        _env_file=None,
        mcp_mode="remote",
        mcp_auth_mode="google_cloud_run",
        mcp_adoption_url="https://adoption.example/mcp",
        mcp_adoption_audience="https://adoption.example",
    )

    assert settings.mcp_places_url is None


def test_remote_mcp_can_enable_only_the_care_plan_service() -> None:
    settings = Settings(
        _env_file=None,
        mcp_mode="remote",
        mcp_auth_mode="google_cloud_run",
        mcp_care_plan_url="https://care.example/mcp",
        mcp_care_plan_audience="https://care.example",
    )

    assert settings.mcp_places_url is None
    assert settings.mcp_adoption_url is None


def test_care_plan_mcp_rejects_public_authentication_mode() -> None:
    with pytest.raises(ValidationError, match="private Cloud Run"):
        Settings(
            _env_file=None,
            mcp_mode="remote",
            mcp_care_plan_url="https://care.example/mcp",
        )


@pytest.mark.asyncio
async def test_care_plan_only_mcp_configuration_builds_api_container() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        mcp_mode="remote",
        mcp_auth_mode="google_cloud_run",
        mcp_care_plan_url="https://care.example/mcp",
        mcp_care_plan_audience="https://care.example",
    )

    container, runtime = await build_configured_container(settings)

    assert container.care_plan_tools is not None
    assert runtime is None
    container.close()


def test_private_mcp_endpoint_requires_an_audience() -> None:
    with pytest.raises(ValidationError, match="requires an audience"):
        Settings(
            _env_file=None,
            mcp_mode="remote",
            mcp_auth_mode="google_cloud_run",
            mcp_places_url="https://places.example/mcp",
        )


def test_url_mode_requires_asyncpg_url() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_mode="url",
        database_url=SecretStr("postgresql+asyncpg://user:secret@localhost/advisor"),
    )

    assert settings.database_url is not None
    assert "secret" not in repr(settings.database_url)


def test_url_mode_rejects_sync_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(
            _env_file=None,
            app_env="test",
            database_mode="url",
            database_url=SecretStr("postgresql+psycopg://user:secret@localhost/advisor"),
        )


def test_cloud_sql_mode_requires_connection_identity() -> None:
    with pytest.raises(ValidationError, match="Missing Cloud SQL settings"):
        Settings(_env_file=None, app_env="staging", database_mode="cloud_sql")


def test_cloud_sql_iam_mode_rejects_password() -> None:
    with pytest.raises(ValidationError, match="DB_PASSWORD must be unset"):
        Settings(
            _env_file=None,
            app_env="staging",
            database_mode="cloud_sql",
            instance_connection_name="project:region:instance",
            db_user="advisor-api@project.iam",
            db_name="advisor",
            db_password=SecretStr("do-not-use"),
        )


def test_cloud_sql_iam_mode_accepts_empty_password_from_env_file() -> None:
    settings = Settings(
        _env_file=None,
        app_env="staging",
        database_mode="cloud_sql",
        instance_connection_name="project:region:instance",
        db_user="advisor-api@project.iam",
        db_name="advisor",
        db_password=SecretStr(""),
    )

    assert settings.cloud_sql_enable_iam_auth is True


def test_provider_secret_whitespace_is_removed() -> None:
    settings = Settings(
        _env_file=None,
        retrieval_mode="pinecone",
        pinecone_api_key=SecretStr(" demo-key\r\n"),
        pinecone_index_host="https://example.svc.pinecone.io",
    )

    assert settings.pinecone_api_key is not None
    assert settings.pinecone_api_key.get_secret_value() == "demo-key"


def test_authoritative_tables_use_dedicated_schema() -> None:
    expected = {
        "advisor.catalog_candidates",
        "advisor.catalog_evidence",
        "advisor.knowledge_sources",
        "advisor.knowledge_chunks",
        "advisor.plant_toxicity",
        "advisor.care_plan_previews",
        "advisor.care_plans",
        "advisor.care_tasks",
    }

    assert {f"{table.schema}.{table.name}" for table in Base.metadata.tables.values()} == expected
    assert all(table.schema == SCHEMA for table in Base.metadata.tables.values())
