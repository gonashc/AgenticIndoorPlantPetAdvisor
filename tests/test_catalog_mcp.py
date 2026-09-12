"""Contract tests for bounded authoritative catalog MCP tools."""

from collections.abc import Mapping, Sequence

import pytest
from advisor_api.adapters.in_memory import InMemoryCatalogRepository
from advisor_api.ports.data import ToxicityClassification
from mcp import Client
from pydantic import SecretStr, ValidationError

from services.catalog_mcp.config import CatalogMcpSettings
from services.catalog_mcp.server import create_server


class StubToxicityRepository:
    async def classify(
        self,
        scientific_names: Sequence[str],
        animal_species: Sequence[str],
    ) -> Mapping[tuple[str, str], ToxicityClassification]:
        assert scientific_names == ("Epipremnum aureum",)
        assert animal_species == ("DOG", "CAT")
        return {
            ("DOG", "epipremnum aureum"): ToxicityClassification.TOXIC,
            ("CAT", "epipremnum aureum"): ToxicityClassification.TOXIC,
        }


def settings() -> CatalogMcpSettings:
    return CatalogMcpSettings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        database_mode="url",
        database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"),
    )


@pytest.mark.asyncio
async def test_catalog_mcp_returns_exact_profiles_constraints_and_provenance() -> None:
    server = create_server(settings(), InMemoryCatalogRepository(), StubToxicityRepository())

    async with Client(server) as client:
        profiles = await client.call_tool(
            "get_profiles",
            {"category": "PLANT", "candidate_ids": ["plant-spider"]},
        )
        constraints = await client.call_tool(
            "get_constraints",
            {"category": "PLANT", "candidate_id": "plant-pothos"},
        )
        provenance = await client.call_tool(
            "get_provenance",
            {"category": "PLANT", "candidate_id": "plant-spider"},
        )

    assert not profiles.is_error
    assert profiles.structured_content is not None
    assert profiles.structured_content["profiles"][0]["name"] == "Spider Plant"
    assert constraints.structured_content is not None
    assert constraints.structured_content["constraints"]["toxic_to_cats"] is True
    assert provenance.structured_content is not None
    assert provenance.structured_content["records"][0]["source_url"].startswith("https://")


@pytest.mark.asyncio
async def test_catalog_mcp_returns_reviewed_toxicity_and_rejects_broad_queries() -> None:
    server = create_server(settings(), InMemoryCatalogRepository(), StubToxicityRepository())

    async with Client(server) as client:
        toxicity = await client.call_tool(
            "get_toxicity",
            {
                "scientific_names": ["Epipremnum aureum"],
                "animal_species": ["DOG", "CAT"],
            },
        )
        too_many = await client.call_tool(
            "get_profiles",
            {
                "category": "PLANT",
                "candidate_ids": [f"plant-{index}" for index in range(11)],
            },
        )

    assert toxicity.structured_content is not None
    assert {fact["classification"] for fact in toxicity.structured_content["facts"]} == {"TOXIC"}
    assert "absent record does not establish safety" in toxicity.structured_content["notice"]
    assert too_many.is_error


def test_catalog_mcp_production_requires_cloud_sql() -> None:
    with pytest.raises(ValidationError, match="requires Cloud SQL"):
        CatalogMcpSettings(
            _env_file=None,  # type: ignore[call-arg]
            app_env="production",
            database_mode="url",
            database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"),
        )
