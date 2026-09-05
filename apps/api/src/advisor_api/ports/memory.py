"""Provider-neutral port for consented preference recall and deletion."""

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID


class PreferenceMemory(Protocol):
    async def recall(self, session_id: UUID) -> Mapping[str, object]: ...

    async def delete(self, session_id: UUID) -> None: ...
