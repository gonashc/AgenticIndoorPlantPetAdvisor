"""Contract and provider tests for the private plant-location MCP service."""

from collections.abc import Sequence

import httpx
import pytest
from mcp import Client
from pydantic import SecretStr

from services.places_mcp.config import PlacesMcpSettings
from services.places_mcp.google_places import GooglePlacesClient, PlaceListing
from services.places_mcp.server import create_server


class StubPlantLocationProvider:
    async def find_plant_nurseries(
        self, *, plant_name: str, zip_code: str, limit: int
    ) -> Sequence[PlaceListing]:
        assert plant_name == "snake plant"
        assert zip_code == "10001"
        assert limit == 3
        return (PlaceListing("Neighborhood Nursery", "https://maps.google.com/?cid=123"),)


def settings() -> PlacesMcpSettings:
    return PlacesMcpSettings(
        _env_file=None,
        app_env="test",
        google_places_api_key=SecretStr("test-key"),
    )


@pytest.mark.asyncio
async def test_google_places_adapter_uses_bounded_field_mask() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        assert request.headers["X-Goog-FieldMask"] == ("places.displayName,places.googleMapsUri")
        assert request.read().count(b"10001") == 1
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "displayName": {"text": "Neighborhood Nursery"},
                        "googleMapsUri": "https://maps.google.com/?cid=123",
                    }
                ]
            },
        )

    provider = GooglePlacesClient(
        api_key="test-key",
        url="https://places.googleapis.com/v1/places:searchText",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )

    listings = await provider.find_plant_nurseries(
        plant_name="snake plant", zip_code="10001", limit=3
    )

    assert listings == (PlaceListing("Neighborhood Nursery", "https://maps.google.com/?cid=123"),)


@pytest.mark.asyncio
async def test_mcp_server_returns_strict_structured_sources() -> None:
    server = create_server(settings(), StubPlantLocationProvider())

    async with Client(server) as client:
        result = await client.call_tool(
            "find_places",
            {
                "category": "PLANT",
                "candidate_id": "snake-plant",
                "zip_code": "10001",
                "limit": 3,
            },
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["sources"][0]["source_type"] == "plant_nursery"
    assert result.structured_content["sources"][0]["confidence"] == "RECENTLY_OBSERVED"


@pytest.mark.asyncio
async def test_mcp_server_rejects_non_plant_calls() -> None:
    server = create_server(settings(), StubPlantLocationProvider())

    async with Client(server) as client:
        result = await client.call_tool(
            "find_places",
            {
                "category": "DOG",
                "candidate_id": "snake-plant",
                "zip_code": "10001",
                "limit": 3,
            },
        )

    assert result.is_error
