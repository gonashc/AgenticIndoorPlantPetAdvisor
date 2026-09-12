"""Contract tests for optional, confirmed commerce lookups."""

import pytest
from mcp import Client

from services.commerce_mcp.config import CommerceMcpSettings
from services.commerce_mcp.providers import CommerceProviderResult, RetailOffer
from services.commerce_mcp.server import create_server


class StubCommerceProvider:
    async def find_offers(
        self,
        *,
        category: str,
        candidate_id: str,
        zip_code: str,
        limit: int,
    ) -> CommerceProviderResult:
        assert (category, candidate_id, zip_code, limit) == (
            "PLANT",
            "plant-spider",
            "10001",
            3,
        )
        return CommerceProviderResult(
            available=True,
            offers=(
                RetailOffer(
                    offer_id="retailer-42",
                    candidate_id="plant-spider",
                    retailer_name="Example Garden Center",
                    product_name="Spider Plant 6 inch",
                    inventory_status="IN_STOCK",
                    price=19.99,
                    currency="USD",
                    pickup_available=True,
                    pickup_location="Manhattan store",
                    product_url="https://shop.example.test/products/spider-plant",
                ),
            ),
        )


def settings() -> CommerceMcpSettings:
    return CommerceMcpSettings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        commerce_allowed_link_hosts="example.test",
    )


@pytest.mark.asyncio
async def test_commerce_mcp_returns_only_allowlisted_confirmed_offers() -> None:
    server = create_server(settings(), StubCommerceProvider())  # type: ignore[arg-type]

    async with Client(server) as client:
        result = await client.call_tool(
            "find_confirmed_offers",
            {
                "category": "PLANT",
                "candidate_id": "plant-spider",
                "zip_code": "10001",
            },
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["status"] == "AVAILABLE"
    assert result.structured_content["offers"][0]["inventory_status"] == "IN_STOCK"
    assert result.structured_content["offers"][0]["confidence"] == "RECENTLY_OBSERVED"


@pytest.mark.asyncio
async def test_commerce_mcp_is_explicitly_unavailable_without_provider() -> None:
    server = create_server(settings())

    async with Client(server) as client:
        result = await client.call_tool(
            "find_confirmed_offers",
            {
                "category": "DOG",
                "candidate_id": "dog-calm-small-adult",
                "zip_code": "10001",
            },
        )

    assert result.structured_content is not None
    assert result.structured_content["status"] == "UNAVAILABLE"
    assert result.structured_content["offers"] == []


@pytest.mark.asyncio
async def test_commerce_mcp_rejects_invalid_destination() -> None:
    server = create_server(settings())

    async with Client(server) as client:
        result = await client.call_tool(
            "find_confirmed_offers",
            {
                "category": "PLANT",
                "candidate_id": "plant-spider",
                "zip_code": "1000",
            },
        )

    assert result.is_error
