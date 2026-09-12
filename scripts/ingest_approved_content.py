"""Validate and index a reviewed-content manifest into PostgreSQL and Pinecone."""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from advisor_api.config import Settings
from advisor_api.contracts.base import Category
from pydantic import BaseModel, ConfigDict, Field

from database.repositories import PostgresIngestionManifestRepository
from database.runtime import create_database_runtime
from services.ingestion import (
    ApprovedContentDocument,
    ApprovedContentIngestionPipeline,
    ContentPolicy,
    ReviewStatus,
    TrustTier,
)
from services.retrieval.pinecone import PineconeHybridKnowledgeAdapter


class ManifestDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    text_path: str
    candidate_ids: list[str] = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.APPROVED
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str
    allowed_licenses: list[str] = Field(min_length=1)
    documents: list[ManifestDocument] = Field(min_length=1)


def load_manifest(path: Path) -> tuple[IngestionManifest, tuple[ApprovedContentDocument, ...]]:
    manifest_path = path.resolve(strict=True)
    root = manifest_path.parent
    manifest = IngestionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    documents: list[ApprovedContentDocument] = []
    for entry in manifest.documents:
        text_path = (root / entry.text_path).resolve(strict=True)
        if not text_path.is_relative_to(root):
            raise ValueError(f"Content path escapes manifest directory: {entry.text_path}")
        documents.append(
            ApprovedContentDocument(
                source_id=entry.source_id,
                category=entry.category,
                title=entry.title,
                publisher=entry.publisher,
                canonical_url=entry.canonical_url,
                license_id=entry.license_id,
                trust_tier=entry.trust_tier,
                retrieved_at=entry.retrieved_at,
                reviewed_at=entry.reviewed_at,
                approved_by=entry.approved_by,
                content_version=entry.content_version,
                text=text_path.read_text(encoding="utf-8"),
                candidate_ids=tuple(entry.candidate_ids),
                review_status=entry.review_status,
                metadata=entry.metadata,
            )
        )
    return manifest, tuple(documents)


async def run(path: Path) -> int:
    settings = Settings()
    if settings.database_mode == "memory":
        raise RuntimeError("Approved ingestion requires PostgreSQL")
    if settings.retrieval_mode != "pinecone":
        raise RuntimeError("Approved ingestion requires RETRIEVAL_MODE=pinecone")
    if settings.pinecone_api_key is None or settings.pinecone_index_host is None:
        raise RuntimeError("Pinecone settings are incomplete")

    manifest, documents = load_manifest(path)
    allowed_trust_tiers = {TrustTier.AUTHORITATIVE, TrustTier.EXPERT_REVIEWED}
    if settings.app_env in {"local", "test"}:
        allowed_trust_tiers.add(TrustTier.DEMO_UNVERIFIED)
    runtime = await create_database_runtime(settings)
    try:
        await runtime.verify()
        pipeline = ApprovedContentIngestionPipeline(
            ContentPolicy(
                allowed_licenses=frozenset(manifest.allowed_licenses),
                allowed_trust_tiers=frozenset(allowed_trust_tiers),
            ),
            PostgresIngestionManifestRepository(runtime.session_factory),
            PineconeHybridKnowledgeAdapter(
                api_key=settings.pinecone_api_key.get_secret_value(),
                index_host=settings.pinecone_index_host,
                index_dimension=settings.pinecone_index_dimension,
                dense_model=settings.pinecone_dense_model,
                sparse_model=settings.pinecone_sparse_model,
                rerank_model=settings.pinecone_rerank_model,
                alpha=settings.pinecone_hybrid_alpha,
                timeout_seconds=settings.pinecone_timeout_seconds,
            ),
        )
        report = await pipeline.ingest(documents, namespace=manifest.namespace)
    finally:
        await runtime.close()
    print(
        f"namespace={report.namespace} accepted={report.accepted_sources} "
        f"chunks={report.indexed_chunks} quarantined={len(report.quarantined)}"
    )
    for item in report.quarantined:
        print(f"quarantined source={item.source_id} reasons={','.join(item.reasons)}")
    return 1 if report.quarantined else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    return asyncio.run(run(args.manifest))


if __name__ == "__main__":
    raise SystemExit(main())
