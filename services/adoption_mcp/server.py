"""MCP server exposing bounded, read-only adoption discovery."""

import re
from datetime import UTC, datetime
from typing import cast

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.adoption_mcp.config import AdoptionMcpSettings
from services.adoption_mcp.contracts import AdoptionSource, FindAdoptionsResult
from services.adoption_mcp.rescuegroups import AdoptionProvider, PetCategory, RescueGroupsClient

_CANDIDATE_ID = re.compile(r"^(dog|cat)-[a-z0-9][a-z0-9_-]{0,75}$")
_ZIP_CODE = re.compile(r"^\d{5}$")


def create_server(
    settings: AdoptionMcpSettings | None = None,
    provider: AdoptionProvider | None = None,
) -> MCPServer[None]:
    resolved = settings or AdoptionMcpSettings()  # type: ignore[call-arg]
    adoption_provider = provider or RescueGroupsClient(
        api_key=resolved.rescuegroups_api_key.get_secret_value(),
        base_url=resolved.rescuegroups_base_url,
        timeout_seconds=resolved.rescuegroups_timeout_seconds,
        radius_miles=resolved.rescuegroups_radius_miles,
        allowed_link_hosts=resolved.allowed_link_hosts(),
    )
    server: MCPServer[None] = MCPServer(
        name="advisor-adoption",
        title="Indoor Plant and Pet Advisor Adoption Service",
        description="Finds current public dog and cat adoption listings after profile ranking.",
        version="1.0.0",
    )

    @server.tool(
        name="find_adoptions",
        description=(
            "Find up to three current public adoption listings near a ZIP code. Results are "
            "recent observations and do not guarantee availability, temperament, or suitability."
        ),
        structured_output=True,
    )
    async def find_adoptions(
        category: str, candidate_id: str, zip_code: str, limit: int = 3
    ) -> FindAdoptionsResult:
        if category not in {"DOG", "CAT"}:
            raise ValueError("find_adoptions accepts only DOG or CAT")
        pet_category = cast(PetCategory, category)
        expected_prefix = category.lower()
        if not _CANDIDATE_ID.fullmatch(candidate_id) or not candidate_id.startswith(
            f"{expected_prefix}-"
        ):
            raise ValueError("candidate_id does not match the selected pet category")
        if not _ZIP_CODE.fullmatch(zip_code):
            raise ValueError("zip_code must contain five digits")
        if not 1 <= limit <= 3:
            raise ValueError("limit must be between 1 and 3")
        listings = await adoption_provider.find_available_animals(
            category=pet_category,
            zip_code=zip_code,
            limit=limit,
        )
        verified_at = datetime.now(UTC)
        return FindAdoptionsResult(
            sources=[
                AdoptionSource(
                    name=item.name,
                    source_type=item.source_type,
                    url=item.url,
                    distance_miles=item.distance_miles,
                    verified_at=verified_at,
                )
                for item in listings
            ]
        )

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "advisor-adoption"})

    return server


def create_app(settings: AdoptionMcpSettings | None = None) -> Starlette:
    resolved = settings or AdoptionMcpSettings()  # type: ignore[call-arg]
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
