"""Contract and provider tests for the private adoption MCP service."""

import json
from collections.abc import Sequence

import httpx
import pytest
from mcp import Client
from pydantic import SecretStr

from services.adoption_mcp.config import AdoptionMcpSettings
from services.adoption_mcp.rescuegroups import AdoptionListing, PetCategory, RescueGroupsClient
from services.adoption_mcp.server import create_server


class StubAdoptionProvider:
    async def find_available_animals(
        self, *, category: PetCategory, zip_code: str, limit: int
    ) -> Sequence[AdoptionListing]:
        assert category == "DOG"
        assert zip_code == "10001"
        assert limit == 3
        return (
            AdoptionListing(
                name="Milo — Mixed Breed · City Rescue",
                source_type="animal_rescue",
                url="https://city.rescuegroups.org/animals/detail?AnimalID=42",
                distance_miles=4.2,
            ),
        )


def settings() -> AdoptionMcpSettings:
    return AdoptionMcpSettings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        rescuegroups_api_key=SecretStr("test-key"),
    )


@pytest.mark.asyncio
async def test_rescuegroups_adapter_uses_bounded_available_search() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "test-key"
        assert request.headers["Content-Type"] == "application/vnd.api+json"
        assert request.url.path == "/v5/public/animals/search/available/dogs/"
        assert request.url.params["limit"] == "3"
        assert request.url.params["sort"] == "distance"
        assert request.url.params["include"] == "orgs"
        request_body = json.loads(request.read())
        assert request_body == {"data": {"filterRadius": {"postalcode": "10001", "miles": 100}}}
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "animals",
                        "id": "42",
                        "attributes": {
                            "name": "Milo",
                            "breedString": "Mixed Breed",
                            "url": ("https://city.rescuegroups.org/animals/detail?AnimalID=42"),
                        },
                        "relationships": {"orgs": {"data": {"type": "orgs", "id": "7"}}},
                        "meta": {"distance": "4.2"},
                    }
                ],
                "included": [
                    {
                        "type": "orgs",
                        "id": "7",
                        "attributes": {"name": "City Rescue", "type": "Rescue"},
                    }
                ],
            },
        )

    provider = RescueGroupsClient(
        api_key="test-key",
        base_url="https://api.rescuegroups.org/v5",
        timeout_seconds=2,
        radius_miles=100,
        allowed_link_hosts=frozenset({"rescuegroups.org"}),
        transport=httpx.MockTransport(handler),
    )

    listings = await provider.find_available_animals(category="DOG", zip_code="10001", limit=3)

    assert listings == (
        AdoptionListing(
            name="Milo — Mixed Breed · City Rescue",
            source_type="animal_rescue",
            url="https://city.rescuegroups.org/animals/detail?AnimalID=42",
            distance_miles=4.2,
        ),
    )


@pytest.mark.asyncio
async def test_rescuegroups_adapter_rejects_unapproved_listing_hosts() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "animals",
                        "id": "42",
                        "attributes": {"name": "Milo", "url": "https://untrusted.example/pet"},
                    }
                ]
            },
        )

    provider = RescueGroupsClient(
        api_key="test-key",
        base_url="https://api.rescuegroups.org/v5",
        timeout_seconds=2,
        radius_miles=100,
        allowed_link_hosts=frozenset({"rescuegroups.org"}),
        transport=httpx.MockTransport(handler),
    )

    listings = await provider.find_available_animals(category="CAT", zip_code="10001", limit=3)

    assert listings == ()


@pytest.mark.asyncio
async def test_adoption_mcp_returns_strict_structured_sources() -> None:
    server = create_server(settings(), StubAdoptionProvider())

    async with Client(server) as client:
        result = await client.call_tool(
            "find_adoptions",
            {
                "category": "DOG",
                "candidate_id": "dog-calm-small-adult",
                "zip_code": "10001",
                "limit": 3,
            },
        )

    assert not result.is_error
    assert result.structured_content is not None
    source = result.structured_content["sources"][0]
    assert source["source_type"] == "animal_rescue"
    assert source["confidence"] == "RECENTLY_OBSERVED"
    assert source["distance_miles"] == 4.2


@pytest.mark.asyncio
async def test_adoption_mcp_rejects_plant_and_mismatched_profiles() -> None:
    server = create_server(settings(), StubAdoptionProvider())

    async with Client(server) as client:
        plant_result = await client.call_tool(
            "find_adoptions",
            {
                "category": "PLANT",
                "candidate_id": "plant-spider",
                "zip_code": "10001",
            },
        )
        mismatch_result = await client.call_tool(
            "find_adoptions",
            {
                "category": "CAT",
                "candidate_id": "dog-calm-small-adult",
                "zip_code": "10001",
            },
        )

    assert plant_result.is_error
    assert mismatch_result.is_error
