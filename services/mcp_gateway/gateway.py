"""Allowlisted live-source MCP calls, intentionally separate from RAG."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from advisor_api.contracts.base import Category, LocalSource

from services.mcp_gateway.ports import McpToolClient


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    url: str
    tool_name: str


class McpCurrentSourceGateway:
    """Fetches ephemeral local listings without persisting or indexing them."""

    _TOOL_BY_CATEGORY = {
        Category.PLANT: "find_places",
        Category.DOG: "find_adoptions",
        Category.CAT: "find_adoptions",
    }

    def __init__(
        self,
        client: McpToolClient,
        *,
        places: McpServerConfig,
        adoption: McpServerConfig,
        timeout_seconds: float = 8.0,
    ) -> None:
        expected = {"find_places", "find_adoptions"}
        if {places.tool_name, adoption.tool_name} != expected:
            raise ValueError("MCP gateway accepts only the approved live-source tools")
        self._client = client
        self._places = places
        self._adoption = adoption
        self._timeout = timeout_seconds

    async def find_sources(
        self,
        *,
        category: Category,
        candidate_id: str,
        zip_code: str,
    ) -> Sequence[LocalSource]:
        config = self._places if category == Category.PLANT else self._adoption
        if config.tool_name != self._TOOL_BY_CATEGORY[category]:
            raise ValueError("MCP server is not authorized for this category")
        payload = await self._client.call_tool(
            server_url=config.url,
            tool_name=config.tool_name,
            arguments={
                "category": category.value,
                "candidate_id": candidate_id,
                "zip_code": zip_code,
                "limit": 3,
            },
            timeout_seconds=self._timeout,
        )
        raw_sources = payload.get("sources", [])
        if not isinstance(raw_sources, list):
            raise ValueError("MCP live-source response must contain a sources list")
        return tuple(self._validate_source(item) for item in raw_sources[:3])

    @staticmethod
    def _validate_source(item: object) -> LocalSource:
        if not isinstance(item, Mapping):
            raise ValueError("MCP live-source items must be objects")
        source = LocalSource.model_validate(item)
        parsed = urlparse(source.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("MCP live-source URLs must use HTTPS")
        if source.verified_at.tzinfo is None or source.verified_at > datetime.now(UTC):
            raise ValueError("MCP verification timestamps must be timezone-aware and not future")
        return source
