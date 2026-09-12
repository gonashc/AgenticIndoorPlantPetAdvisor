"""Provider-neutral ports for authoritative catalog and plan persistence."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from advisor_api.contracts.base import Category, CostEstimate, EvidenceReference
from advisor_api.contracts.care_plans import CarePlan, CarePlanPreviewResponse


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """Minimal structured record consumed by recommendation intelligence."""

    candidate_id: str
    category: Category
    name: str
    scientific_name: str | None
    profile: str
    features: Mapping[str, float]
    care_summary: tuple[str, ...]
    cost: CostEstimate
    evidence: tuple[EvidenceReference, ...]
    toxic_to_children: bool = False
    toxic_to_dogs: bool = False
    toxic_to_cats: bool = False
    allowed_housing: frozenset[str] = frozenset({"APARTMENT", "CONDO", "HOUSE"})
    child_compatible: bool = True
    dog_compatible: bool = True
    cat_compatible: bool = True
    max_hours_alone: float = 24
    content_version: str = "unknown"


class CatalogRepository(Protocol):
    async def list_candidates(self, category: Category) -> Sequence[CandidateRecord]: ...


class ToxicityClassification(StrEnum):
    TOXIC = "TOXIC"
    NON_TOXIC_LISTED = "NON_TOXIC_LISTED"


class PlantToxicityRepository(Protocol):
    async def classify(
        self,
        scientific_names: Sequence[str],
        animal_species: Sequence[str],
    ) -> Mapping[tuple[str, str], ToxicityClassification]: ...


class PreviewClaimStatus(StrEnum):
    CLAIMED = "CLAIMED"
    NOT_FOUND = "NOT_FOUND"
    EXPIRED = "EXPIRED"
    ALREADY_CONSUMED = "ALREADY_CONSUMED"


class CarePlanRepository(Protocol):
    async def save_preview(
        self, preview: CarePlanPreviewResponse, owner_id: UUID
    ) -> CarePlanPreviewResponse: ...

    async def get_preview(
        self, preview_id: UUID, owner_id: UUID
    ) -> CarePlanPreviewResponse | None: ...

    async def confirm_preview(
        self,
        preview_id: UUID,
        owner_id: UUID,
        claimed_at: datetime,
        plan: CarePlan,
    ) -> PreviewClaimStatus: ...

    async def get(self, plan_id: UUID, owner_id: UUID) -> CarePlan | None: ...

    async def update(
        self, plan: CarePlan, owner_id: UUID, *, expected_version: int
    ) -> CarePlan | None: ...
