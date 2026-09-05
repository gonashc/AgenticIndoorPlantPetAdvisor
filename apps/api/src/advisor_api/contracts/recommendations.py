"""Recommendation request and response contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from advisor_api.contracts.base import (
    Category,
    ContractModel,
    CostEstimate,
    Destination,
    EvidenceReference,
    LocalSource,
    RequestMetadata,
    ValidationStatus,
)


class PlantQuestionnaire(ContractModel):
    light_level: Literal["LOW", "MEDIUM", "BRIGHT_INDIRECT", "DIRECT"]
    humidity: Literal["LOW", "AVERAGE", "HIGH"]
    indoor_temperature_f: int = Field(ge=50, le=95)
    available_space: Literal["SMALL", "MEDIUM", "LARGE"]
    experience: Literal["BEGINNER", "INTERMEDIATE", "EXPERT"]
    watering_availability: Literal["LOW", "MEDIUM", "HIGH"]
    monthly_budget: float = Field(ge=0, le=1000)
    children_present: bool = False
    pets_present: set[Literal["DOG", "CAT"]] = Field(default_factory=set)


class PetQuestionnaire(ContractModel):
    housing_type: Literal["APARTMENT", "CONDO", "HOUSE"]
    home_size: Literal["SMALL", "MEDIUM", "LARGE"]
    rental_allows_pets: bool
    outdoor_space: Literal["NONE", "BALCONY", "YARD"]
    hours_alone: float = Field(ge=0, le=24)
    activity_level: Literal["LOW", "MEDIUM", "HIGH"]
    grooming_tolerance: Literal["LOW", "MEDIUM", "HIGH"]
    monthly_budget: float = Field(ge=0, le=5000)
    children_present: bool = False
    existing_pets: set[Literal["DOG", "CAT"]] = Field(default_factory=set)
    experience: Literal["BEGINNER", "INTERMEDIATE", "EXPERT"]


class CatQuestionnaire(PetQuestionnaire):
    affection_preference: Literal["INDEPENDENT", "BALANCED", "AFFECTIONATE"]


class RecommendationRequestBase(ContractModel):
    destination: Destination
    session_id: UUID
    use_saved_preferences: bool = False


class PlantRecommendationRequest(RecommendationRequestBase):
    category: Literal[Category.PLANT]
    questionnaire: PlantQuestionnaire


class DogRecommendationRequest(RecommendationRequestBase):
    category: Literal[Category.DOG]
    questionnaire: PetQuestionnaire


class CatRecommendationRequest(RecommendationRequestBase):
    category: Literal[Category.CAT]
    questionnaire: CatQuestionnaire


type RecommendationRequest = Annotated[
    PlantRecommendationRequest | DogRecommendationRequest | CatRecommendationRequest,
    Field(discriminator="category"),
]


class SafetyDisclosure(ContractModel):
    child_toxicity: Literal["TOXIC", "NON_TOXIC", "UNKNOWN", "NOT_APPLICABLE"]
    dog_toxicity: Literal["TOXIC", "NON_TOXIC", "UNKNOWN", "NOT_APPLICABLE"]
    cat_toxicity: Literal["TOXIC", "NON_TOXIC", "UNKNOWN", "NOT_APPLICABLE"]
    hard_constraints_passed: Literal[True] = True


class RecommendationItem(ContractModel):
    recommendation_id: str
    name: str
    scientific_name: str | None = None
    profile: str
    score: int = Field(ge=0, le=100)
    best_match: bool
    reasons: list[str] = Field(min_length=3)
    concerns: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(min_length=1)
    local_sources: list[LocalSource] = Field(default_factory=list, max_length=3)
    care_summary: list[str] = Field(min_length=1)
    cost: CostEstimate
    safety: SafetyDisclosure

    @model_validator(mode="after")
    def best_match_requires_threshold(self) -> "RecommendationItem":
        if self.best_match and self.score < 60:
            raise ValueError("Best Match requires a score of at least 60")
        return self


class RecommendationResponse(ContractModel):
    metadata: RequestMetadata
    session_id: UUID
    category: Category
    recommendations: list[RecommendationItem] = Field(min_length=1, max_length=3)
    validation_status: ValidationStatus
    warnings: list[str] = Field(default_factory=list)
