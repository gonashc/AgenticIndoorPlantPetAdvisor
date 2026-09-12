"""Models for reviewed sources, deterministic chunks, and ingestion outcomes."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from advisor_api.contracts.base import Category


class ReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    QUARANTINED = "QUARANTINED"


class TrustTier(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    EXPERT_REVIEWED = "EXPERT_REVIEWED"
    DEMO_UNVERIFIED = "DEMO_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class ApprovedContentDocument:
    source_id: str
    category: Category
    title: str
    publisher: str
    canonical_url: str
    license_id: str
    trust_tier: TrustTier
    retrieved_at: datetime
    reviewed_at: datetime
    approved_by: str
    content_version: str
    text: str
    candidate_ids: tuple[str, ...]
    review_status: ReviewStatus = ReviewStatus.APPROVED
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContentChunk:
    chunk_id: str
    source_id: str
    category: Category
    candidate_ids: tuple[str, ...]
    position: int
    text: str
    text_sha256: str
    word_count: int
    title: str
    publisher: str
    canonical_url: str
    reviewed_at: datetime
    content_version: str
    namespace: str
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QuarantinedContent:
    source_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IngestionReport:
    namespace: str
    accepted_sources: int
    indexed_chunks: int
    quarantined: tuple[QuarantinedContent, ...]
    manifest_version: str = "chunk-manifest-v1"
