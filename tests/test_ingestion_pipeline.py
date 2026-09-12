"""Approved-content ingestion safety and determinism tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from advisor_api.contracts.base import Category

from services.ingestion import (
    ApprovedContentDocument,
    ApprovedContentIngestionPipeline,
    ContentPolicy,
    ReviewStatus,
    TrustTier,
)
from services.ingestion.ports import (
    InMemoryIngestionManifestRepository,
    InMemoryKnowledgeIndexWriter,
)


def document(**changes: object) -> ApprovedContentDocument:
    values: dict[str, object] = {
        "source_id": "aspca-spider-plant-v1",
        "category": Category.PLANT,
        "title": "Spider plant care and safety",
        "publisher": "Example university extension",
        "canonical_url": "https://extension.example.edu/spider-plant",
        "license_id": "CC-BY-4.0",
        "trust_tier": TrustTier.EXPERT_REVIEWED,
        "retrieved_at": datetime(2026, 9, 1, tzinfo=UTC),
        "reviewed_at": datetime(2026, 9, 2, tzinfo=UTC),
        "approved_by": "reviewer-42",
        "content_version": "2026-09-02",
        "text": " ".join(f"reviewed-word-{index}" for index in range(420)),
        "candidate_ids": ("plant-spider",),
    }
    values.update(changes)
    return ApprovedContentDocument(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_pipeline_indexes_only_approved_content_and_is_deterministic() -> None:
    manifest = InMemoryIngestionManifestRepository()
    index = InMemoryKnowledgeIndexWriter()
    pipeline = ApprovedContentIngestionPipeline(
        ContentPolicy(frozenset({"CC-BY-4.0"}), chunk_words=100, overlap_words=20),
        manifest,
        index,
    )

    first = await pipeline.ingest(
        [document()], namespace="knowledge-candidate-v1", now=datetime(2026, 9, 9, tzinfo=UTC)
    )
    chunk_key = ("knowledge-candidate-v1", "aspca-spider-plant-v1")
    first_ids = tuple(chunk.chunk_id for chunk in index.chunks[chunk_key])
    second = await pipeline.ingest(
        [document()], namespace="knowledge-candidate-v1", now=datetime(2026, 9, 9, tzinfo=UTC)
    )
    second_ids = tuple(chunk.chunk_id for chunk in index.chunks[chunk_key])

    assert first.accepted_sources == second.accepted_sources == 1
    assert first.indexed_chunks == second.indexed_chunks == 5
    assert first_ids == second_ids
    assert manifest.indexed == {("aspca-spider-plant-v1", "knowledge-candidate-v1")}


@pytest.mark.asyncio
async def test_pipeline_quarantines_unapproved_or_stale_sources() -> None:
    manifest = InMemoryIngestionManifestRepository()
    index = InMemoryKnowledgeIndexWriter()
    pipeline = ApprovedContentIngestionPipeline(
        ContentPolicy(frozenset({"CC-BY-4.0"}), maximum_review_age=timedelta(days=30)),
        manifest,
        index,
    )

    report = await pipeline.ingest(
        [
            document(
                canonical_url="http://untrusted.example/content",
                license_id="UNKNOWN",
                review_status=ReviewStatus.QUARANTINED,
                reviewed_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
        ],
        namespace="knowledge-candidate-v1",
        now=datetime(2026, 9, 9, tzinfo=UTC),
    )

    assert report.accepted_sources == 0
    assert report.indexed_chunks == 0
    assert set(report.quarantined[0].reasons) == {
        "SOURCE_URL_NOT_HTTPS",
        "SOURCE_NOT_APPROVED",
        "LICENSE_NOT_ALLOWED",
        "REVIEW_OUTSIDE_FRESHNESS_WINDOW",
    }
    assert not index.chunks


@pytest.mark.asyncio
async def test_demo_content_requires_an_explicit_demo_policy() -> None:
    manifest = InMemoryIngestionManifestRepository()
    index = InMemoryKnowledgeIndexWriter()
    demo_document = replace(document(), trust_tier=TrustTier.DEMO_UNVERIFIED)

    report = await ApprovedContentIngestionPipeline(
        ContentPolicy(allowed_licenses=frozenset({"CC-BY-4.0"})),
        manifest,
        index,
    ).ingest(
        [demo_document],
        namespace="knowledge-v1",
        now=datetime(2026, 9, 9, tzinfo=UTC),
    )

    assert report.accepted_sources == 0
    assert report.quarantined[0].reasons == ("TRUST_TIER_NOT_ALLOWED",)
