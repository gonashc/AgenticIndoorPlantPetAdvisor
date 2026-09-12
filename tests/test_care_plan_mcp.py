"""Authentication and confirmation tests for care-plan MCP actions."""

from uuid import UUID

import pytest
from advisor_api.adapters.auth import LocalIdentityTokenVerifier
from advisor_api.adapters.in_memory import InMemoryCarePlanRepository
from mcp import Client
from pydantic import SecretStr, ValidationError

from services.care_plan_mcp.config import CarePlanMcpSettings
from services.care_plan_mcp.server import create_server
from services.care_plans.service import CarePlanService


def settings() -> CarePlanMcpSettings:
    return CarePlanMcpSettings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        auth_mode="disabled",
        enabled_categories="PLANT,DOG,CAT",
        database_mode="url",
        database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"),
    )


def server_with_memory_repository():  # type: ignore[no-untyped-def]
    service = CarePlanService(
        InMemoryCarePlanRepository(),
        frozenset({"PLANT", "DOG", "CAT"}),
    )
    return create_server(settings(), service, LocalIdentityTokenVerifier())


@pytest.mark.asyncio
async def test_care_plan_mcp_requires_preview_and_literal_confirmation() -> None:
    server = server_with_memory_repository()

    async with Client(server) as client:
        tools = await client.list_tools()
        preview = await client.call_tool(
            "preview_care_plan",
            {
                "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
                "recommendation_id": "plant-spider",
                "category": "PLANT",
                "item_name": "Spider Plant",
                "start_date": "2026-09-12",
                "timezone": "America/New_York",
            },
        )
        assert preview.structured_content is not None
        preview_id = preview.structured_content["preview"]["preview_id"]
        rejected = await client.call_tool(
            "create_care_plan",
            {"preview_id": preview_id, "confirmed": False},
        )
        created = await client.call_tool(
            "create_care_plan",
            {"preview_id": preview_id, "confirmed": True},
        )

    assert all("owner_id" not in tool.input_schema.get("properties", {}) for tool in tools.tools)
    assert rejected.is_error
    assert not created.is_error
    assert created.structured_content is not None
    assert created.structured_content["plan"]["status"] == "ACTIVE"
    UUID(created.structured_content["plan"]["plan_id"])


@pytest.mark.asyncio
async def test_care_plan_mcp_adjusts_and_completes_owner_scoped_plan() -> None:
    server = server_with_memory_repository()

    async with Client(server) as client:
        preview = await client.call_tool(
            "preview_care_plan",
            {
                "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
                "recommendation_id": "dog-calm-small-adult",
                "category": "DOG",
                "item_name": "Calm Small Adult Dog Profile",
                "start_date": "2026-09-12",
                "timezone": "America/New_York",
            },
        )
        assert preview.structured_content is not None
        created = await client.call_tool(
            "create_care_plan",
            {
                "preview_id": preview.structured_content["preview"]["preview_id"],
                "confirmed": True,
            },
        )
        assert created.structured_content is not None
        plan = created.structured_content["plan"]
        completed = await client.call_tool(
            "complete_care_task",
            {"plan_id": plan["plan_id"], "task_id": plan["tasks"][0]["task_id"]},
        )
        paused = await client.call_tool(
            "adjust_care_plan",
            {"plan_id": plan["plan_id"], "status": "PAUSED"},
        )

    assert completed.structured_content is not None
    assert completed.structured_content["plan"]["tasks"][0]["completed_at"] is not None
    assert paused.structured_content is not None
    assert paused.structured_content["plan"]["status"] == "PAUSED"


def test_production_care_plan_mcp_requires_iap() -> None:
    with pytest.raises(ValidationError, match="requires Google IAP"):
        CarePlanMcpSettings(
            _env_file=None,  # type: ignore[call-arg]
            app_env="production",
            auth_mode="disabled",
            database_mode="cloud_sql",
            database_url=None,
            instance_connection_name="project:region:instance",
            db_user="advisor-care-plan",
            db_name="advisor",
        )
