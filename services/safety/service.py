"""Hard exclusions that cannot be overridden by an LLM or optimizer."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from advisor_api.contracts.recommendations import (
    CatRecommendationRequest,
    DogRecommendationRequest,
    PlantRecommendationRequest,
    RecommendationRequest,
)
from advisor_api.ports.data import (
    CandidateRecord,
    PlantToxicityRepository,
    ToxicityClassification,
)


class SafetyService:
    def __init__(self, toxicity_repository: PlantToxicityRepository | None = None) -> None:
        self._toxicity = toxicity_repository

    async def filter_candidates(
        self,
        request: RecommendationRequest,
        candidates: Sequence[CandidateRecord],
    ) -> tuple[CandidateRecord, ...]:
        resolved = await self._apply_structured_toxicity(candidates)
        return tuple(candidate for candidate in resolved if self._is_allowed(request, candidate))

    async def _apply_structured_toxicity(
        self, candidates: Sequence[CandidateRecord]
    ) -> tuple[CandidateRecord, ...]:
        if self._toxicity is None:
            return tuple(candidates)
        scientific_names = tuple(
            candidate.scientific_name
            for candidate in candidates
            if candidate.category.value == "PLANT" and candidate.scientific_name
        )
        classifications = await self._toxicity.classify(scientific_names, ("DOG", "CAT"))
        return tuple(self._with_toxicity(candidate, classifications) for candidate in candidates)

    @staticmethod
    def _with_toxicity(
        candidate: CandidateRecord,
        classifications: Mapping[tuple[str, str], ToxicityClassification],
    ) -> CandidateRecord:
        if candidate.scientific_name is None:
            return candidate
        normalized = " ".join(candidate.scientific_name.casefold().split()).rstrip(".")
        dog = classifications.get(("DOG", normalized))
        cat = classifications.get(("CAT", normalized))
        return replace(
            candidate,
            toxic_to_dogs=(dog == ToxicityClassification.TOXIC)
            if dog is not None
            else candidate.toxic_to_dogs,
            toxic_to_cats=(cat == ToxicityClassification.TOXIC)
            if cat is not None
            else candidate.toxic_to_cats,
        )

    @staticmethod
    def _is_allowed(request: RecommendationRequest, candidate: CandidateRecord) -> bool:
        if isinstance(request, PlantRecommendationRequest):
            plant_questionnaire = request.questionnaire
            return not (
                (plant_questionnaire.children_present and candidate.toxic_to_children)
                or ("DOG" in plant_questionnaire.pets_present and candidate.toxic_to_dogs)
                or ("CAT" in plant_questionnaire.pets_present and candidate.toxic_to_cats)
            )

        if isinstance(request, (DogRecommendationRequest, CatRecommendationRequest)):
            pet_questionnaire = request.questionnaire
            return (
                pet_questionnaire.rental_allows_pets
                and pet_questionnaire.housing_type in candidate.allowed_housing
                and pet_questionnaire.hours_alone <= candidate.max_hours_alone
                and (not pet_questionnaire.children_present or candidate.child_compatible)
                and ("DOG" not in pet_questionnaire.existing_pets or candidate.dog_compatible)
                and ("CAT" not in pet_questionnaire.existing_pets or candidate.cat_compatible)
            )

        return False
