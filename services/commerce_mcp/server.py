"""MCP server for bounded, confirmed retailer inventory lookups."""

import re
from datetime import UTC, datetime
from typing import Literal, cast
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.commerce_mcp.config import CommerceMcpSettings
from services.commerce_mcp.contracts import CommerceLookupResult, CommerceOffer
from services.commerce_mcp.providers import CommerceProvider, DisabledCommerceProvider

_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")


def create_server(
    settings: CommerceMcpSettings | None = None,
    provider: CommerceProvider | None = None,
) -> MCPServer[None]:
    resolved = settings or CommerceMcpSettings()
    commerce_provider = provider or DisabledCommerceProvider()
    allowed_hosts = resolved.allowed_link_hosts()
    server: MCPServer[None] = MCPServer(
        name="advisor-commerce",
        title="Indoor Plant and Pet Advisor Commerce Service",
        description="Returns bounded, recently confirmed retailer inventory and pricing.",
        version="1.0.0",
    )

    @server.tool(
        name="find_confirmed_offers",
        description=(
            "Return at most three provider-confirmed offers for an already-selected candidate. "
            "Offers cannot affect recommendation ranking or safety."
        ),
        structured_output=True,
    )
    async def find_confirmed_offers(
        category: str,
        candidate_id: str,
        zip_code: str,
        limit: int = 3,
    ) -> CommerceLookupResult:
        if category not in {"PLANT", "DOG", "CAT"}:
            raise ValueError("category must be PLANT, DOG, or CAT")
        if not _CANDIDATE_ID.fullmatch(candidate_id):
            raise ValueError("candidate_id has an invalid format")
        if not re.fullmatch(r"\d{5}", zip_code):
            raise ValueError("zip_code must contain five digits")
        if not 1 <= limit <= 3:
            raise ValueError("limit must be between 1 and 3")
        selected_category = cast(Literal["PLANT", "DOG", "CAT"], category)
        result = await commerce_provider.find_offers(
            category=selected_category,
            candidate_id=candidate_id,
            zip_code=zip_code,
            limit=limit,
        )
        verified_at = datetime.now(UTC)
        offers = []
        for item in result.offers[:limit]:
            if item.candidate_id != candidate_id:
                raise ValueError("Commerce provider returned an offer for another candidate")
            _validate_product_url(item.product_url, allowed_hosts)
            offers.append(
                CommerceOffer(
                    offer_id=item.offer_id,
                    candidate_id=item.candidate_id,
                    retailer_name=item.retailer_name,
                    product_name=item.product_name,
                    inventory_status=item.inventory_status,
                    price=item.price,
                    currency=item.currency,
                    pickup_available=item.pickup_available,
                    pickup_location=item.pickup_location,
                    product_url=item.product_url,
                    verified_at=verified_at,
                )
            )
        status: Literal["AVAILABLE", "UNAVAILABLE"] = (
            "AVAILABLE" if result.available else "UNAVAILABLE"
        )
        if status == "UNAVAILABLE" and offers:
            raise ValueError("Unavailable commerce providers cannot return offers")
        return CommerceLookupResult(
            status=status,
            candidate_id=candidate_id,
            zip_code=zip_code,
            offers=offers,
        )

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok" if provider is not None else "degraded",
                "service": "advisor-commerce",
                "provider": "configured" if provider is not None else "disabled",
            }
        )

    return server


def create_app(settings: CommerceMcpSettings | None = None) -> Starlette:
    resolved = settings or CommerceMcpSettings()
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


def _validate_product_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    host = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme != "https"
        or not host
        or not any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)
    ):
        raise ValueError("Commerce provider returned a product URL outside the allowlist")
