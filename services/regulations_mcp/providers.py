"""Provider port for current, government-supported pet rules."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

PetCategory = Literal["DOG", "CAT"]
RegulationTopic = Literal[
    "LICENSING",
    "LEASH_OR_RESTRAINT",
    "VACCINATION",
    "ANIMAL_LIMIT",
    "HOUSING",
    "TRAVEL_OR_MOVEMENT",
    "OTHER",
]
JurisdictionLevel = Literal["STATE", "CITY", "COUNTY"]


@dataclass(frozen=True, slots=True)
class RegulationRecord:
    rule_id: str
    category: PetCategory
    jurisdiction: str
    jurisdiction_level: JurisdictionLevel
    topic: RegulationTopic
    summary: str
    effective_on: date | None
    source_title: str
    source_url: str
    source_version: str


@dataclass(frozen=True, slots=True)
class RegulationProviderResult:
    available: bool
    rules: Sequence[RegulationRecord]


class RegulationProvider(Protocol):
    async def lookup(
        self,
        *,
        category: PetCategory,
        state_code: str,
        city: str | None,
        limit: int,
    ) -> RegulationProviderResult: ...


class DisabledRegulationProvider:
    """Safe fallback used until a reviewed live provider is configured."""

    async def lookup(
        self,
        *,
        category: PetCategory,
        state_code: str,
        city: str | None,
        limit: int,
    ) -> RegulationProviderResult:
        del category, state_code, city, limit
        return RegulationProviderResult(available=False, rules=())
