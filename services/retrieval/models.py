"""Stable, provider-neutral knowledge retrieval models."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from advisor_api.contracts.base import Category


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    """A bounded query over approved knowledge for already-eligible candidates."""

    category: Category
    text: str
    candidate_ids: tuple[str, ...]
    namespace: str
    top_k: int = 12
    rerank_top_n: int = 5
    filters: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Knowledge query text cannot be empty")
        if not self.candidate_ids:
            raise ValueError("Knowledge queries require at least one candidate ID")
        if not self.namespace.strip():
            raise ValueError("Knowledge namespace cannot be empty")
        if self.top_k < 1 or self.rerank_top_n < 1:
            raise ValueError("Knowledge result limits must be positive")
        if self.rerank_top_n > self.top_k:
            raise ValueError("Rerank limit cannot exceed retrieval limit")


@dataclass(frozen=True, slots=True)
class KnowledgePassage:
    """One approved passage returned independently of a vector-store payload."""

    chunk_id: str
    source_id: str
    candidate_id: str
    category: Category
    text: str
    score: float
    title: str
    source_name: str
    source_url: str
    reviewed_at: datetime
    content_version: str
    namespace: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.source_id or not self.candidate_id:
            raise ValueError("Knowledge passage identifiers cannot be empty")
        if not self.text.strip():
            raise ValueError("Knowledge passage text cannot be empty")
        if not 0 <= self.score <= 1:
            raise ValueError("Knowledge passage score must be normalized between 0 and 1")
        if not self.namespace.strip():
            raise ValueError("Knowledge passage namespace cannot be empty")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Knowledge passage source URL must use HTTPS")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("Knowledge passage review timestamp must be timezone-aware")
