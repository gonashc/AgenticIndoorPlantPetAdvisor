"""MCP server exposing only bounded plant-location discovery."""

import re
from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.places_mcp.config import PlacesMcpSettings
from services.places_mcp.contracts import FindPlacesResult, PlantLocationSource
from services.places_mcp.google_places import GooglePlacesClient, PlantLocationProvider

_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_ZIP_CODE = re.compile(r"^\d{5}$")


def create_server(
    settings: PlacesMcpSettings | None = None,
    provider: PlantLocationProvider | None = None,
) -> MCPServer[None]:
    resolved = settings or PlacesMcpSettings()  # type: ignore[call-arg]
    location_provider = provider or GooglePlacesClient(
        api_key=resolved.google_places_api_key.get_secret_value(),
        url=resolved.google_places_url,
        timeout_seconds=resolved.google_places_timeout_seconds,
    )
    server: MCPServer[None] = MCPServer(
        name="advisor-plant-location",
        title="Indoor Plant Advisor Location Service",
        description="Finds nearby plant nurseries after recommendations are finalized.",
        version="1.0.0",
    )

    @server.tool(
        name="find_places",
        description=(
            "Find up to three nearby plant nurseries. Results are discovery links and do not "
            "confirm plant inventory, suitability, price, ranking, or safety."
        ),
        structured_output=True,
    )
    async def find_places(
        category: str, candidate_id: str, zip_code: str, limit: int = 3
    ) -> FindPlacesResult:
        if category != "PLANT":
            raise ValueError("find_places accepts only the PLANT category")
        if not _CANDIDATE_ID.fullmatch(candidate_id):
            raise ValueError("candidate_id has an invalid format")
        if not _ZIP_CODE.fullmatch(zip_code):
            raise ValueError("zip_code must contain five digits")
        if not 1 <= limit <= 3:
            raise ValueError("limit must be between 1 and 3")
        plant_name = candidate_id.replace("-", " ").replace("_", " ")
        listings = await location_provider.find_plant_nurseries(
            plant_name=plant_name,
            zip_code=zip_code,
            limit=limit,
        )
        verified_at = datetime.now(UTC)
        return FindPlacesResult(
            sources=[
                PlantLocationSource(
                    name=item.name,
                    url=item.maps_url,
                    verified_at=verified_at,
                )
                for item in listings
            ]
        )

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "advisor-plant-location"})

    return server


def create_app(settings: PlacesMcpSettings | None = None) -> Starlette:
    resolved = settings or PlacesMcpSettings()  # type: ignore[call-arg]
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
