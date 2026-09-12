"""Deterministic validation, chunking, indexing, and quarantine pipeline."""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from services.ingestion.models import (
    ApprovedContentDocument,
    ContentChunk,
    IngestionReport,
    QuarantinedContent,
    ReviewStatus,
    TrustTier,
)
from services.ingestion.ports import IngestionManifestRepository, KnowledgeIndexWriter

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ContentPolicy:
    allowed_licenses: frozenset[str]
    allowed_trust_tiers: frozenset[TrustTier] = frozenset(
        {TrustTier.AUTHORITATIVE, TrustTier.EXPERT_REVIEWED}
    )
    maximum_review_age: timedelta = timedelta(days=365)
    chunk_words: int = 180
    overlap_words: int = 30

    def __post_init__(self) -> None:
        if not self.allowed_licenses:
            raise ValueError("At least one content license must be allowlisted")
        if not self.allowed_trust_tiers:
            raise ValueError("At least one trust tier must be allowlisted")
        if self.chunk_words < 50:
            raise ValueError("Chunk size must be at least 50 words")
        if not 0 <= self.overlap_words < self.chunk_words:
            raise ValueError("Chunk overlap must be non-negative and smaller than chunk size")


class ApprovedContentIngestionPipeline:
    def __init__(
        self,
        policy: ContentPolicy,
        manifest: IngestionManifestRepository,
        index: KnowledgeIndexWriter,
    ) -> None:
        self._policy = policy
        self._manifest = manifest
        self._index = index

    async def ingest(
        self,
        documents: Iterable[ApprovedContentDocument],
        *,
        namespace: str,
        now: datetime | None = None,
    ) -> IngestionReport:
        if not namespace.strip():
            raise ValueError("Ingestion namespace cannot be empty")
        observed_at = now or datetime.now(UTC)
        accepted_sources = 0
        indexed_chunks = 0
        quarantined: list[QuarantinedContent] = []

        for document in documents:
            reasons = self._validate(document, observed_at)
            if reasons:
                rejected = QuarantinedContent(document.source_id, tuple(reasons))
                await self._manifest.quarantine(document, rejected)
                quarantined.append(rejected)
                continue

            chunks = self._chunk(document, namespace)
            await self._manifest.begin_source(document, chunks)
            await self._index.replace_source(
                namespace=namespace,
                source_id=document.source_id,
                chunks=chunks,
            )
            await self._manifest.mark_indexed(document.source_id, namespace)
            accepted_sources += 1
            indexed_chunks += len(chunks)

        return IngestionReport(
            namespace=namespace,
            accepted_sources=accepted_sources,
            indexed_chunks=indexed_chunks,
            quarantined=tuple(quarantined),
        )

    def _validate(self, document: ApprovedContentDocument, now: datetime) -> list[str]:
        reasons: list[str] = []
        parsed = urlparse(document.canonical_url)
        if parsed.scheme != "https" or not parsed.hostname:
            reasons.append("SOURCE_URL_NOT_HTTPS")
        if document.review_status != ReviewStatus.APPROVED:
            reasons.append("SOURCE_NOT_APPROVED")
        if document.license_id not in self._policy.allowed_licenses:
            reasons.append("LICENSE_NOT_ALLOWED")
        if document.trust_tier not in self._policy.allowed_trust_tiers:
            reasons.append("TRUST_TIER_NOT_ALLOWED")
        if not document.approved_by.strip():
            reasons.append("REVIEWER_REQUIRED")
        if document.reviewed_at.tzinfo is None or document.retrieved_at.tzinfo is None:
            reasons.append("TIMESTAMPS_MUST_BE_TIMEZONE_AWARE")
        elif (
            document.reviewed_at > now
            or now - document.reviewed_at > self._policy.maximum_review_age
        ):
            reasons.append("REVIEW_OUTSIDE_FRESHNESS_WINDOW")
        if not document.candidate_ids:
            reasons.append("CANDIDATE_SCOPE_REQUIRED")
        if len(_normalize(document.text).split()) < 20:
            reasons.append("CONTENT_TOO_SHORT")
        return reasons

    def _chunk(self, document: ApprovedContentDocument, namespace: str) -> tuple[ContentChunk, ...]:
        words = _normalize(document.text).split()
        step = self._policy.chunk_words - self._policy.overlap_words
        chunks: list[ContentChunk] = []
        for position, start in enumerate(range(0, len(words), step)):
            chunk_words = words[start : start + self._policy.chunk_words]
            if not chunk_words:
                break
            text = " ".join(chunk_words)
            text_sha256 = hashlib.sha256(text.encode()).hexdigest()
            identity = (
                f"{namespace}:{document.source_id}:{document.content_version}:"
                f"{position}:{text_sha256}"
            )
            chunk_id = hashlib.sha256(identity.encode()).hexdigest()[:40]
            chunks.append(
                ContentChunk(
                    chunk_id=chunk_id,
                    source_id=document.source_id,
                    category=document.category,
                    candidate_ids=document.candidate_ids,
                    position=position,
                    text=text,
                    text_sha256=text_sha256,
                    word_count=len(chunk_words),
                    title=document.title,
                    publisher=document.publisher,
                    canonical_url=document.canonical_url,
                    reviewed_at=document.reviewed_at,
                    content_version=document.content_version,
                    namespace=namespace,
                    metadata=document.metadata,
                )
            )
            if start + self._policy.chunk_words >= len(words):
                break
        return tuple(chunks)


def _normalize(text: str) -> str:
    return _SPACE.sub(" ", text).strip()
