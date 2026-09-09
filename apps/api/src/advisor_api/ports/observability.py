"""Provider-neutral observability ports."""

from contextlib import AbstractContextManager
from typing import Literal, Protocol
from uuid import UUID

from advisor_api.contracts.base import Category

TraceTransport = Literal["http", "stream"]


class RecommendationTracer(Protocol):
    """Scopes a recommendation workflow without exposing provider details."""

    def trace(
        self,
        *,
        request_id: UUID,
        category: Category,
        transport: TraceTransport,
    ) -> AbstractContextManager[None]: ...

    def close(self) -> None: ...
