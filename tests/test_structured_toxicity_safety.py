"""Structured toxicity facts remain authoritative over catalog flags."""

from collections.abc import Sequence

import pytest
from advisor_api.adapters.in_memory import InMemoryCatalogRepository
from advisor_api.contracts.recommendations import PlantRecommendationRequest
from advisor_api.ports.data import ToxicityClassification

from services.safety import SafetyService


class ToxicSpiderPlantRepository:
    async def classify(
        self, scientific_names: Sequence[str], animal_species: Sequence[str]
    ) -> dict[tuple[str, str], ToxicityClassification]:
        assert "Chlorophytum comosum" in scientific_names
        assert animal_species == ("DOG", "CAT")
        return {("CAT", "chlorophytum comosum"): ToxicityClassification.TOXIC}


@pytest.mark.asyncio
async def test_structured_toxicity_overrides_catalog_safety_flag(
    plant_payload: dict[str, object],
) -> None:
    request = PlantRecommendationRequest.model_validate(plant_payload)
    candidates = await InMemoryCatalogRepository().list_candidates(request.category)

    eligible = await SafetyService(ToxicSpiderPlantRepository()).filter_candidates(
        request, candidates
    )

    assert "plant-spider" not in {candidate.candidate_id for candidate in eligible}
