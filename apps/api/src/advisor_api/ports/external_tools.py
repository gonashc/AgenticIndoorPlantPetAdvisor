"""Provider-neutral port for current places, adoption, climate, rules, and web data."""

from collections.abc import Sequence
from typing import Protocol

from advisor_api.contracts.base import Category, LocalSource


class CurrentSourceGateway(Protocol):
    async def find_sources(
        self,
        *,
        category: Category,
        candidate_id: str,
        zip_code: str,
    ) -> Sequence[LocalSource]: ...
