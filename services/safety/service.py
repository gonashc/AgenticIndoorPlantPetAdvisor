"""Hard exclusions that cannot be overridden by an LLM or optimizer."""

from collections.abc import Sequence

from advisor_api.contracts.recommendations import (
    CatRecommendationRequest,
    DogRecommendationRequest,
    PlantRecommendationRequest,
    RecommendationRequest,
)
from advisor_api.ports.data import CandidateRecord


class SafetyService:
    def filter_candidates(
        self,
        request: RecommendationRequest,
        candidates: Sequence[CandidateRecord],
    ) -> tuple[CandidateRecord, ...]:
        return tuple(candidate for candidate in candidates if self._is_allowed(request, candidate))

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
