"""Contract tests for the source-constrained regulations MCP service."""

from datetime import date

import pytest
from mcp import Client

from services.regulations_mcp.config import RegulationsMcpSettings
from services.regulations_mcp.providers import RegulationProviderResult, RegulationRecord
from services.regulations_mcp.server import create_server


class StubRegulationProvider:
    async def lookup(
        self,
        *,
        category: str,
        state_code: str,
        city: str | None,
        limit: int,
    ) -> RegulationProviderResult:
        assert (category, state_code, city, limit) == ("DOG", "NY", "New York", 5)
        return RegulationProviderResult(
            available=True,
            rules=(
                RegulationRecord(
                    rule_id="nyc-dog-license-v1",
                    category="DOG",
                    jurisdiction="New York City, NY",
                    jurisdiction_level="CITY",
                    topic="LICENSING",
                    summary="Dogs living in New York City require a current license.",
                    effective_on=date(2026, 1, 1),
                    source_title="Dog licensing",
                    source_url="https://www.nyc.gov/site/doh/services/dog-licenses.page",
                    source_version="retrieved-2026-09-12",
                ),
            ),
        )


def settings() -> RegulationsMcpSettings:
    return RegulationsMcpSettings(_env_file=None, app_env="test")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_regulations_mcp_returns_cited_government_rules() -> None:
    server = create_server(settings(), StubRegulationProvider())  # type: ignore[arg-type]

    async with Client(server) as client:
        result = await client.call_tool(
            "lookup_pet_regulations",
            {"category": "DOG", "state_code": "ny", "city": "New York"},
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["status"] == "AVAILABLE"
    assert result.structured_content["rules"][0]["topic"] == "LICENSING"
    assert result.structured_content["rules"][0]["source_url"].startswith("https://www.nyc.gov")


@pytest.mark.asyncio
async def test_regulations_mcp_is_explicitly_unavailable_without_provider() -> None:
    server = create_server(settings())

    async with Client(server) as client:
        result = await client.call_tool(
            "lookup_pet_regulations",
            {"category": "CAT", "state_code": "NJ", "city": "Jersey City"},
        )

    assert result.structured_content is not None
    assert result.structured_content["status"] == "UNAVAILABLE"
    assert result.structured_content["rules"] == []


@pytest.mark.asyncio
async def test_regulations_mcp_rejects_non_pet_category() -> None:
    server = create_server(settings())

    async with Client(server) as client:
        result = await client.call_tool(
            "lookup_pet_regulations",
            {"category": "PLANT", "state_code": "NY"},
        )

    assert result.is_error
