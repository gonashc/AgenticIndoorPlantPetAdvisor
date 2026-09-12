"""Tests for the isolated, allowlisted MCP live-data boundary."""

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from advisor_api.contracts.base import Category, Confidence

from services.mcp_gateway import McpCurrentSourceGateway, McpServerConfig


class StubMcpClient:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: Mapping[str, object],
        timeout_seconds: float,
        authorization_audience: str | None = None,
    ) -> Mapping[str, object]:
        assert timeout_seconds in {4, 8}
        assert authorization_audience is None
        self.calls.append((server_url, tool_name, arguments))
        return self.response


@pytest.mark.asyncio
async def test_live_gateway_routes_categories_to_allowlisted_tools() -> None:
    client = StubMcpClient(
        {
            "sources": [
                {
                    "name": "Neighborhood nursery",
                    "source_type": "retailer",
                    "url": "https://example.invalid/nursery",
                    "distance_miles": 2.4,
                    "verified_at": datetime.now(UTC).isoformat(),
                    "confidence": "CONFIRMED",
                }
            ]
        }
    )
    gateway = McpCurrentSourceGateway(
        client,
        places=McpServerConfig("https://places.example/mcp", "find_places"),
        adoption=McpServerConfig("https://adoption.example/mcp", "find_adoptions"),
        timeout_seconds=4,
    )

    sources = await gateway.find_sources(
        category=Category.PLANT,
        candidate_id="plant-1",
        zip_code="10001",
    )

    assert sources[0].confidence == Confidence.CONFIRMED
    assert client.calls[0][0:2] == ("https://places.example/mcp", "find_places")
    assert client.calls[0][2]["limit"] == 3


@pytest.mark.asyncio
async def test_live_gateway_rejects_untrusted_urls() -> None:
    client = StubMcpClient(
        {
            "sources": [
                {
                    "name": "Unsafe source",
                    "source_type": "retailer",
                    "url": "http://example.invalid/source",
                    "verified_at": datetime.now(UTC).isoformat(),
                    "confidence": "UNVERIFIED",
                }
            ]
        }
    )
    gateway = McpCurrentSourceGateway(
        client,
        places=McpServerConfig("https://places.example/mcp", "find_places"),
        adoption=McpServerConfig("https://adoption.example/mcp", "find_adoptions"),
    )

    with pytest.raises(ValueError, match="HTTPS"):
        await gateway.find_sources(
            category=Category.PLANT,
            candidate_id="plant-1",
            zip_code="10001",
        )


def test_live_gateway_rejects_unapproved_tool_names() -> None:
    with pytest.raises(ValueError, match="approved live-source tools"):
        McpCurrentSourceGateway(
            StubMcpClient({}),
            places=McpServerConfig("https://places.example/mcp", "read_file"),
            adoption=McpServerConfig("https://adoption.example/mcp", "find_adoptions"),
        )
