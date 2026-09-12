"""Provider-neutral knowledge retrieval boundary."""

from collections.abc import Sequence
from typing import Protocol

from services.retrieval.models import KnowledgePassage, KnowledgeQuery


class KnowledgeRetriever(Protocol):
    async def retrieve(self, query: KnowledgeQuery) -> Sequence[KnowledgePassage]: ...


class EmptyKnowledgeRetriever:
    """Safe fallback used until an approved knowledge namespace is enabled."""

    async def retrieve(self, query: KnowledgeQuery) -> tuple[KnowledgePassage, ...]:
        del query
        return ()
