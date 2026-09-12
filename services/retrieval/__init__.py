"""Provider-neutral retrieval contracts and adapters."""

from services.retrieval.models import KnowledgePassage, KnowledgeQuery
from services.retrieval.ports import EmptyKnowledgeRetriever, KnowledgeRetriever

__all__ = [
    "EmptyKnowledgeRetriever",
    "KnowledgePassage",
    "KnowledgeQuery",
    "KnowledgeRetriever",
]
