"""MCP server for bounded, source-validated current pet regulations."""

import re
from datetime import UTC, datetime
from typing import Literal, cast
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.regulations_mcp.config import RegulationsMcpSettings
from services.regulations_mcp.contracts import RegulationLookupResult, RegulationRule
from services.regulations_mcp.providers import (
    DisabledRegulationProvider,
    PetCategory,
    RegulationProvider,
)

_CITY = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,99}$")


def create_server(
    settings: RegulationsMcpSettings | None = None,
    provider: RegulationProvider | None = None,
) -> MCPServer[None]:
    resolved = settings or RegulationsMcpSettings()
    regulation_provider = provider or DisabledRegulationProvider()
    allowed_hosts = resolved.allowed_source_hosts()
    server: MCPServer[None] = MCPServer(
        name="advisor-regulations",
        title="Indoor Plant and Pet Advisor Regulations Service",
        description="Returns bounded current pet rules backed by cited government sources.",
        version="1.0.0",
    )

    @server.tool(
        name="lookup_pet_regulations",
        description=(
            "Return up to eight recently verified state/city pet rules. Results are informational "
            "and must retain their government-source citations."
        ),
        structured_output=True,
    )
    async def lookup_pet_regulations(
        category: str,
        state_code: str,
        city: str | None = None,
        limit: int = 5,
    ) -> RegulationLookupResult:
        if category not in {"DOG", "CAT"}:
            raise ValueError("lookup_pet_regulations accepts only DOG or CAT")
        normalized_state = state_code.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", normalized_state):
            raise ValueError("state_code must contain two letters")
        normalized_city = city.strip() if city is not None else None
        if normalized_city is not None and not _CITY.fullmatch(normalized_city):
            raise ValueError("city has an invalid format")
        if not 1 <= limit <= 8:
            raise ValueError("limit must be between 1 and 8")
        result = await regulation_provider.lookup(
            category=cast(PetCategory, category),
            state_code=normalized_state,
            city=normalized_city,
            limit=limit,
        )
        verified_at = datetime.now(UTC)
        rules = []
        for item in result.rules[:limit]:
            if item.category != category:
                raise ValueError("Regulation provider returned a mismatched category")
            _validate_government_url(item.source_url, allowed_hosts)
            rules.append(
                RegulationRule(
                    rule_id=item.rule_id,
                    category=item.category,
                    jurisdiction=item.jurisdiction,
                    jurisdiction_level=item.jurisdiction_level,
                    topic=item.topic,
                    summary=item.summary,
                    effective_on=item.effective_on,
                    source_title=item.source_title,
                    source_url=item.source_url,
                    source_version=item.source_version,
                    verified_at=verified_at,
                )
            )
        status: Literal["AVAILABLE", "UNAVAILABLE"] = (
            "AVAILABLE" if result.available else "UNAVAILABLE"
        )
        if status == "UNAVAILABLE" and rules:
            raise ValueError("Unavailable regulation providers cannot return rules")
        return RegulationLookupResult(
            status=status,
            category=cast(Literal["DOG", "CAT"], category),
            state_code=normalized_state,
            city=normalized_city,
            rules=rules,
        )

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok" if provider is not None else "degraded",
                "service": "advisor-regulations",
                "provider": "configured" if provider is not None else "disabled",
            }
        )

    return server


def create_app(settings: RegulationsMcpSettings | None = None) -> Starlette:
    resolved = settings or RegulationsMcpSettings()
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


def _validate_government_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    host = parsed.hostname.lower() if parsed.hostname else ""
    government_suffix = host.endswith(".gov") or host.endswith(".us")
    explicitly_allowed = any(
        host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts
    )
    if parsed.scheme != "https" or not host or not (government_suffix or explicitly_allowed):
        raise ValueError("Regulation provider returned a non-government source URL")
