"""Provider port for current, government-supported pet rules."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from services.you_search import YouSearchClient

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
    discovery_sources: Sequence["RegulationDiscoveryRecord"] = ()


@dataclass(frozen=True, slots=True)
class RegulationDiscoveryRecord:
    title: str
    url: str
    description: str


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


class YouComRegulationDiscoveryProvider:
    """Discovers official pages without promoting search snippets into rules."""

    def __init__(self, client: YouSearchClient) -> None:
        self._client = client

    async def lookup(
        self,
        *,
        category: PetCategory,
        state_code: str,
        city: str | None,
        limit: int,
    ) -> RegulationProviderResult:
        jurisdiction = f"{city}, {state_code}" if city else state_code
        query = (
            f"official {jurisdiction} {category.lower()} licensing vaccination restraint "
            "animal regulations (site:.gov OR site:.us)"
        )
        results = await self._client.search(query=query, limit=min(limit, 5))
        return RegulationProviderResult(
            available=False,
            rules=(),
            discovery_sources=tuple(
                RegulationDiscoveryRecord(
                    title=item.title,
                    url=item.url,
                    description=item.description,
                )
                for item in results
            ),
        )
