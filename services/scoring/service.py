"""Deterministic, explainable scoring; no model may alter these results."""

from dataclasses import dataclass

from advisor_api.contracts.recommendations import (
    CatRecommendationRequest,
    DogRecommendationRequest,
    PetQuestionnaire,
    PlantQuestionnaire,
    PlantRecommendationRequest,
    RecommendationRequest,
)
from advisor_api.ports.data import CandidateRecord


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: int
    reasons: tuple[str, ...]
    concerns: tuple[str, ...]


class ScoringService:
    PLANT_WEIGHTS = {
        "light": 0.25,
        "humidity": 0.15,
        "temperature": 0.15,
        "maintenance": 0.15,
        "budget": 0.10,
        "experience": 0.10,
        "space": 0.10,
    }
    PET_WEIGHTS = {
        "home": 0.20,
        "activity": 0.20,
        "climate": 0.15,
        "time_alone": 0.15,
        "grooming": 0.10,
        "budget": 0.10,
        "family": 0.10,
    }

    def score(self, request: RecommendationRequest, candidate: CandidateRecord) -> ScoreResult:
        if isinstance(request, PlantRecommendationRequest):
            desired = self._plant_desired(request.questionnaire)
            weights = self.PLANT_WEIGHTS
        elif isinstance(request, (DogRecommendationRequest, CatRecommendationRequest)):
            desired = self._pet_desired(request.questionnaire)
            weights = self.PET_WEIGHTS
        else:  # pragma: no cover - union exhaustiveness guard
            raise TypeError("Unsupported recommendation request")

        matches: dict[str, float] = {}
        for dimension in weights:
            if dimension == "budget":
                matches[dimension] = min(
                    1.0,
                    request.questionnaire.monthly_budget / max(candidate.cost.monthly_max, 1),
                )
            elif dimension in {"climate", "family"}:
                matches[dimension] = 1.0
            else:
                matches[dimension] = 1 - abs(desired[dimension] - candidate.features[dimension])

        score = round(sum(weights[key] * matches[key] for key in weights) * 100)
        ordered = sorted(matches.items(), key=lambda item: item[1], reverse=True)
        reasons = tuple(
            f"Strong {dimension.replace('_', ' ')} fit ({round(match * 100)}%)."
            for dimension, match in ordered[:3]
        )
        concerns = tuple(
            f"The {dimension.replace('_', ' ')} fit may require adjustment."
            for dimension, match in ordered
            if match < 0.55
        )
        return ScoreResult(score=max(0, min(100, score)), reasons=reasons, concerns=concerns)

    @staticmethod
    def _plant_desired(questionnaire: PlantQuestionnaire) -> dict[str, float]:
        return {
            "light": {"LOW": 0.1, "MEDIUM": 0.4, "BRIGHT_INDIRECT": 0.7, "DIRECT": 1.0}[
                questionnaire.light_level
            ],
            "humidity": {"LOW": 0.1, "AVERAGE": 0.5, "HIGH": 0.9}[questionnaire.humidity],
            "temperature": (questionnaire.indoor_temperature_f - 50) / 45,
            "maintenance": {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.9}[
                questionnaire.watering_availability
            ],
            "experience": {"BEGINNER": 0.1, "INTERMEDIATE": 0.5, "EXPERT": 0.9}[
                questionnaire.experience
            ],
            "space": {"SMALL": 0.2, "MEDIUM": 0.5, "LARGE": 0.9}[questionnaire.available_space],
        }

    @staticmethod
    def _pet_desired(questionnaire: PetQuestionnaire) -> dict[str, float]:
        return {
            "home": {"SMALL": 0.2, "MEDIUM": 0.55, "LARGE": 0.9}[questionnaire.home_size],
            "activity": {"LOW": 0.2, "MEDIUM": 0.55, "HIGH": 0.9}[questionnaire.activity_level],
            "time_alone": min(questionnaire.hours_alone / 12, 1),
            "grooming": {"LOW": 0.2, "MEDIUM": 0.55, "HIGH": 0.9}[questionnaire.grooming_tolerance],
        }
