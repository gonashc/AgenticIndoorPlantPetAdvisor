"""Pinecone adapter contract tests with provider payload fakes."""

from datetime import UTC, datetime
from typing import Any

import pytest
from advisor_api.contracts.base import Category
from pinecone.errors import NotFoundError

from services.ingestion.models import ContentChunk
from services.retrieval.models import KnowledgeQuery
from services.retrieval.pinecone import PineconeHybridKnowledgeAdapter


class FakeInference:
    def __init__(self) -> None:
        self.rerank_documents: list[str] = []
        self.embed_parameters: list[tuple[str, dict[str, object]]] = []

    def embed(
        self, model: str, inputs: list[str], parameters: dict[str, object]
    ) -> list[dict[str, object]]:
        self.embed_parameters.append((model, parameters))
        if "sparse" in model:
            return [{"sparse_indices": [1, 7], "sparse_values": [2.0, 1.0]} for _ in inputs]
        return [{"values": [0.25, 0.75]} for _ in inputs]

    def rerank(
        self,
        model: str,
        query: str,
        documents: list[str],
        rank_fields: list[str],
        return_documents: bool,
        top_n: int,
    ) -> dict[str, object]:
        del model, query, rank_fields, return_documents
        self.rerank_documents = documents
        return {"data": [{"index": 1, "score": 0.92}, {"index": 0, "score": 0.71}][:top_n]}


class FakeIndex:
    def __init__(self, *, namespace_missing: bool = False) -> None:
        self.deleted: dict[str, object] | None = None
        self.upserted: list[dict[str, object]] = []
        self.query_arguments: dict[str, object] = {}
        self.namespace_missing = namespace_missing

    def delete(self, **arguments: object) -> None:
        self.deleted = arguments
        if self.namespace_missing:
            raise NotFoundError("Namespace not found")

    def upsert(self, **arguments: Any) -> None:
        self.upserted = list(arguments["vectors"])

    def query(self, **arguments: object) -> dict[str, object]:
        self.query_arguments = arguments
        metadata = self.upserted[0]["metadata"]
        return {
            "matches": [
                {"id": "chunk-low", "metadata": metadata},
                {"id": "chunk-best", "metadata": metadata},
            ]
        }


class FakePinecone:
    def __init__(self, *, namespace_missing: bool = False) -> None:
        self.inference = FakeInference()
        self.index = FakeIndex(namespace_missing=namespace_missing)

    def Index(self, *, host: str) -> FakeIndex:  # noqa: N802 - provider API shape
        assert host == "example-index-host"
        return self.index


def chunk() -> ContentChunk:
    return ContentChunk(
        chunk_id="chunk-1",
        source_id="source-1",
        category=Category.PLANT,
        candidate_ids=("plant-spider",),
        position=0,
        text="Spider plants prefer bright indirect light and moderate watering.",
        text_sha256="a" * 64,
        word_count=9,
        title="Spider plant guidance",
        publisher="Extension service",
        canonical_url="https://extension.example.edu/spider",
        reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
        content_version="2026-09",
        namespace="knowledge-v1",
    )


@pytest.mark.asyncio
async def test_adapter_indexes_hybrid_vectors_then_reranks_results() -> None:
    provider = FakePinecone()
    adapter = PineconeHybridKnowledgeAdapter(
        api_key="test-key",
        index_host="example-index-host",
        index_dimension=512,
        dense_model="dense-model",
        sparse_model="sparse-model",
        rerank_model="rerank-model",
        alpha=0.75,
        client=provider,
    )

    await adapter.replace_source(namespace="knowledge-v1", source_id="source-1", chunks=[chunk()])
    results = await adapter.retrieve(
        KnowledgeQuery(
            category=Category.PLANT,
            text="pet-safe plant for indirect light",
            candidate_ids=("plant-spider",),
            namespace="knowledge-v1",
            top_k=5,
            rerank_top_n=2,
        )
    )

    assert provider.index.deleted is not None
    assert provider.index.upserted[0]["sparse_values"] == {
        "indices": [1, 7],
        "values": [2.0, 1.0],
    }
    assert provider.index.query_arguments["vector"] == [0.1875, 0.5625]
    assert provider.index.query_arguments["sparse_vector"] == {
        "indices": [1, 7],
        "values": [0.5, 0.25],
    }
    dense_parameters = [
        parameters
        for model, parameters in provider.inference.embed_parameters
        if model == "dense-model"
    ]
    assert dense_parameters == [
        {"input_type": "passage", "truncate": "END", "dimension": 512},
        {"input_type": "query", "truncate": "END", "dimension": 512},
    ]
    assert [passage.chunk_id for passage in results] == ["chunk-best", "chunk-low"]
    assert [passage.score for passage in results] == [0.92, 0.71]


@pytest.mark.asyncio
async def test_first_ingestion_continues_when_namespace_does_not_exist() -> None:
    provider = FakePinecone(namespace_missing=True)
    adapter = PineconeHybridKnowledgeAdapter(
        api_key="test-key",
        index_host="example-index-host",
        index_dimension=512,
        dense_model="dense-model",
        sparse_model="sparse-model",
        rerank_model="rerank-model",
        client=provider,
    )

    await adapter.replace_source(namespace="knowledge-v1", source_id="source-1", chunks=[chunk()])

    assert len(provider.index.upserted) == 1
