"""Provider-neutral port for current places, adoption, climate, rules, and web data."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from advisor_api.contracts.base import Category, LocalSource
from advisor_api.contracts.recommendations import LiveAdvisory


class CurrentSourceGateway(Protocol):
    async def find_sources(
        self,
        *,
        category: Category,
        candidate_id: str,
        zip_code: str,
    ) -> Sequence[LocalSource]: ...


@dataclass(frozen=True, slots=True)
class LiveContextResult:
    advisories: tuple[LiveAdvisory, ...] = ()
    warnings: tuple[str, ...] = ()


class LiveContextGateway(Protocol):
    """Fetch advisory-only context after deterministic selection is complete."""

    async def enrich(
        self,
        *,
        category: Category,
        candidate_ids: Sequence[str],
        zip_code: str,
        state_code: str | None,
    ) -> LiveContextResult: ...
