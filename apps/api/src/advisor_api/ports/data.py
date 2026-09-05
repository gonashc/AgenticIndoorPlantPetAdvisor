"""Provider-neutral ports for authoritative catalog and plan persistence."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from advisor_api.contracts.base import Category, CostEstimate, EvidenceReference
from advisor_api.contracts.care_plans import CarePlan


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


class CatalogRepository(Protocol):
    async def list_candidates(self, category: Category) -> Sequence[CandidateRecord]: ...


class CarePlanRepository(Protocol):
    async def save(self, plan: CarePlan) -> CarePlan: ...

    async def get(self, plan_id: UUID) -> CarePlan | None: ...

    async def update(self, plan: CarePlan) -> CarePlan: ...
