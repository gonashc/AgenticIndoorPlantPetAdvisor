"""Tests for advisory-only MCP orchestration after deterministic ranking."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest
from advisor_api.contracts.base import Category

from services.mcp_gateway import McpLiveContextGateway, McpServerConfig


class StubClient:
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
        del server_url, timeout_seconds, authorization_audience, forwarded_user_assertion
        now = datetime.now(UTC) - timedelta(seconds=1)
        if tool_name == "get_weather_for_zip":
            assert arguments["zip_code"] == "10001"
            return {
                "city": "New York",
                "state_code": "NY",
                "retrieved_at": now.isoformat(),
                "forecast": {
                    "temperature": 70,
                    "temperature_unit": "F",
                    "short_forecast": "Clear",
                    "source_url": "https://api.weather.gov/forecast",
                },
                "alerts": [],
            }
        if tool_name == "lookup_pet_regulations":
            assert arguments["city"] == "New York"
            return {
                "retrieved_at": now.isoformat(),
                "rules": [],
                "discovery_sources": [
                    {
                        "title": "NYC pet rules",
                        "url": "https://www.nyc.gov/pets",
                        "description": "Review current city pet requirements.",
                        "verified_at": now.isoformat(),
                    }
                ],
            }
        return {
            "retrieved_at": now.isoformat(),
            "results": [
                {
                    "title": "CDC cat guidance",
                    "url": "https://www.cdc.gov/healthy-pets/cats",
                    "description": "Current healthy-cat guidance.",
                }
            ],
        }


@pytest.mark.asyncio
async def test_live_context_routes_resolved_city_without_changing_candidates() -> None:
    gateway = McpLiveContextGateway(
        StubClient(),
        climate=McpServerConfig("https://climate.example/mcp", "get_weather_for_zip"),
        regulations=McpServerConfig("https://regulations.example/mcp", "lookup_pet_regulations"),
        web_guidance=McpServerConfig("https://you.example/mcp", "search_current_guidance"),
    )

    result = await gateway.enrich(
        category=Category.CAT,
        candidate_ids=("cat-calm-adult",),
        zip_code="10001",
        state_code=None,
    )

    assert [item.kind for item in result.advisories] == [
        "CLIMATE",
        "REGULATION",
        "WEB_GUIDANCE",
    ]
    assert result.warnings == ()
