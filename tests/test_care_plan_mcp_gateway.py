"""Tests for authenticated API-to-Care-Plan-MCP calls."""

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from advisor_api.contracts.base import Category
from advisor_api.contracts.care_plans import CarePlanPreviewRequest

from services.mcp_gateway import CarePlanMcpGateway, McpSdkToolClient


class AssertionCapturingMcpClient:
    def __init__(self) -> None:
        self.call: dict[str, object] = {}
        self.arguments: Mapping[str, object] = {}

    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: Mapping[str, object],
        timeout_seconds: float,
        authorization_audience: str | None = None,
        forwarded_user_assertion: str | None = None,
    ) -> Mapping[str, object]:
        self.call = {
            "server_url": server_url,
            "tool_name": tool_name,
            "arguments": arguments,
            "timeout_seconds": timeout_seconds,
            "authorization_audience": authorization_audience,
            "forwarded_user_assertion": forwarded_user_assertion,
        }
        self.arguments = arguments
        now = datetime.now(UTC)
        return {
            "preview": {
                "metadata": {
                    "request_id": str(uuid4()),
                    "generated_at": now.isoformat(),
                    "versions": {},
                },
                "preview_id": str(uuid4()),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
                "session_id": arguments["session_id"],
                "recommendation_id": arguments["recommendation_id"],
                "category": arguments["category"],
                "item_name": arguments["item_name"],
                "timezone": arguments["timezone"],
                "tasks": [
                    {
                        "task_id": str(uuid4()),
                        "title": "Check soil moisture",
                        "instructions": "Water only when the plant-specific trigger is met.",
                        "cadence": "WEEKLY",
                        "next_due_on": arguments["start_date"],
                        "completed_at": None,
                    }
                ],
                "confirmation_required": True,
            }
        }


@pytest.mark.asyncio
async def test_care_plan_gateway_forwards_assertion_as_transport_metadata() -> None:
    client = AssertionCapturingMcpClient()
    gateway = CarePlanMcpGateway(
        client,
        "https://care.example/mcp",
        "https://care.example",
        timeout_seconds=4,
    )
    session_id = uuid4()

    preview = await gateway.preview(
        CarePlanPreviewRequest(
            session_id=session_id,
            recommendation_id="plant-spider",
            category=Category.PLANT,
            item_name="Spider plant",
            start_date=date(2026, 9, 12),
            timezone="America/New_York",
        ),
        user_assertion="signed-iap-assertion",
    )

    assert preview.session_id == session_id
    assert client.call["tool_name"] == "preview_care_plan"
    assert client.call["authorization_audience"] == "https://care.example"
    assert client.call["forwarded_user_assertion"] == "signed-iap-assertion"
    assert "owner_id" not in client.arguments


@pytest.mark.asyncio
async def test_sdk_refuses_to_forward_assertion_to_public_service() -> None:
    client = McpSdkToolClient()

    with pytest.raises(ValueError, match="authenticated MCP"):
        await client.call_tool(
            server_url="https://public.example/mcp",
            tool_name="preview_care_plan",
            arguments={},
            timeout_seconds=4,
            forwarded_user_assertion="signed-iap-assertion",
        )


@pytest.mark.parametrize("assertion", ["", "token\r\nInjected: value"])
@pytest.mark.asyncio
async def test_sdk_rejects_invalid_forwarded_assertions(assertion: str) -> None:
    client = McpSdkToolClient()

    with pytest.raises(ValueError, match="invalid"):
        await client.call_tool(
            server_url="https://private.example/mcp",
            tool_name="preview_care_plan",
            arguments={},
            timeout_seconds=4,
            authorization_audience="https://private.example",
            forwarded_user_assertion=assertion,
        )
