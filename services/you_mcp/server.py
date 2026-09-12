"""MCP server exposing bounded You.com current guidance search."""

import re
from datetime import UTC, datetime
from typing import Literal, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.you_mcp.config import YouMcpSettings
from services.you_mcp.contracts import GuidanceResult, SearchCurrentGuidanceResult
from services.you_search import YouSearchClient

_CANDIDATE_ID = re.compile(r"^(plant|dog|cat)-[a-z0-9][a-z0-9_-]{0,75}$")


def create_server(
    settings: YouMcpSettings | None = None,
    provider: YouSearchClient | None = None,
) -> MCPServer[None]:
    resolved = settings or YouMcpSettings()
    search_provider = provider
    if search_provider is None and resolved.you_provider == "api":
        if resolved.you_api_key is None:
            raise ValueError("You.com provider configuration is incomplete")
        search_provider = YouSearchClient(
            api_key=resolved.you_api_key.get_secret_value(),
            base_url=resolved.you_search_url,
            timeout_seconds=resolved.you_timeout_seconds,
            allowed_source_hosts=resolved.allowed_source_hosts(),
        )
    server: MCPServer[None] = MCPServer(
        name="advisor-you-guidance",
        title="Indoor Plant and Pet Advisor Current Guidance Service",
        description="Returns bounded, allowlisted current web guidance from You.com search.",
        version="1.0.0",
    )

    @server.tool(
        name="search_current_guidance",
        description=(
            "Search allowlisted sources using an internally constructed query for up to three "
            "already-ranked candidates. Arbitrary user search strings are not accepted."
        ),
        structured_output=True,
    )
    async def search_current_guidance(
        category: str,
        candidate_ids: list[str],
        state_code: str | None = None,
        limit: int = 3,
    ) -> SearchCurrentGuidanceResult:
        if category not in {"PLANT", "DOG", "CAT"}:
            raise ValueError("category must be PLANT, DOG, or CAT")
        if not 1 <= len(candidate_ids) <= 3 or any(
            not _CANDIDATE_ID.fullmatch(value) for value in candidate_ids
        ):
            raise ValueError("candidate_ids must contain one to three approved candidate IDs")
        normalized_state = state_code.strip().upper() if state_code else None
        if normalized_state is not None and not re.fullmatch(r"[A-Z]{2}", normalized_state):
            raise ValueError("state_code must contain two letters")
        if not 1 <= limit <= 5:
            raise ValueError("limit must be between 1 and 5")
        if search_provider is None:
            raise RuntimeError("Current web guidance provider is unavailable")
        subject = " ".join(candidate_ids)
        region = f" {normalized_state}" if normalized_state else ""
        query = f"current {category.lower()} care safety guidance{region} {subject}"
        results = await search_provider.search(query=query, limit=limit)
        return SearchCurrentGuidanceResult(
            category=cast(Literal["PLANT", "DOG", "CAT"], category),
            candidate_ids=candidate_ids,
            retrieved_at=datetime.now(UTC),
            results=[
                GuidanceResult(title=item.title, url=item.url, description=item.description)
                for item in results
            ],
        )

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok" if search_provider is not None else "degraded",
                "service": "advisor-you-guidance",
            }
        )

    return server


def create_app(settings: YouMcpSettings | None = None) -> Starlette:
    resolved = settings or YouMcpSettings()
    server = create_server(resolved)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=resolved.allowed_hosts(),
        allowed_origins=[],
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=64 * 1024,
        transport_security=security,
        host="0.0.0.0",
    )
