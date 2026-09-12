"""Pinecone single-index hybrid retrieval and reranking adapter."""

import asyncio
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import datetime
from typing import Any

from advisor_api.contracts.base import Category
from pinecone import Pinecone
from pinecone.errors import NotFoundError

from services.ingestion.models import ContentChunk
from services.retrieval.models import KnowledgePassage, KnowledgeQuery


class PineconeHybridKnowledgeAdapter:
    """Writes approved chunks and retrieves them with dense+sparse hybrid search."""

    def __init__(
        self,
        *,
        api_key: str,
        index_host: str,
        index_dimension: int,
        dense_model: str,
        sparse_model: str,
        rerank_model: str,
        alpha: float = 0.65,
        timeout_seconds: float = 10.0,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip() or not index_host.strip():
            raise ValueError("Pinecone API key and index host are required")
        if index_dimension < 1:
            raise ValueError("Pinecone index dimension must be positive")
        if not 0 <= alpha <= 1:
            raise ValueError("Pinecone hybrid alpha must be between 0 and 1")
        self._client: Any = client or Pinecone(api_key=api_key, timeout=timeout_seconds)
        self._index: Any = self._client.Index(host=index_host)
        self._inference: Any = self._client.inference
        self._index_dimension = index_dimension
        self._dense_model = dense_model
        self._sparse_model = sparse_model
        self._rerank_model = rerank_model
        self._alpha = alpha
        self._timeout_seconds = timeout_seconds

    async def replace_source(
        self,
        *,
        namespace: str,
        source_id: str,
        chunks: Sequence[ContentChunk],
    ) -> None:
        if not chunks:
            raise ValueError("Cannot index an empty source")
        texts = [chunk.text for chunk in chunks]
        dense_result, sparse_result = await asyncio.gather(
            asyncio.to_thread(
                self._inference.embed,
                self._dense_model,
                texts,
                {
                    "input_type": "passage",
                    "truncate": "END",
                    "dimension": self._index_dimension,
                },
            ),
            asyncio.to_thread(
                self._inference.embed,
                self._sparse_model,
                texts,
                {"input_type": "passage", "truncate": "END"},
            ),
        )
        dense_embeddings = list(dense_result)
        sparse_embeddings = list(sparse_result)
        if len(dense_embeddings) != len(chunks) or len(sparse_embeddings) != len(chunks):
            raise RuntimeError("Pinecone embedding count did not match the chunk count")

        records = [
            {
                "id": chunk.chunk_id,
                "values": _float_values(dense),
                "sparse_values": _sparse_values(sparse),
                "metadata": _chunk_metadata(chunk),
            }
            for chunk, dense, sparse in zip(
                chunks, dense_embeddings, sparse_embeddings, strict=True
            )
        ]
        # A brand-new namespace has no prior source vectors to replace.
        with suppress(NotFoundError):
            await asyncio.to_thread(
                self._index.delete,
                namespace=namespace,
                filter={"source_id": {"$eq": source_id}},
                timeout=self._timeout_seconds,
            )
        await asyncio.to_thread(
            self._index.upsert,
            vectors=records,
            namespace=namespace,
            show_progress=False,
            timeout=self._timeout_seconds,
        )

    async def retrieve(self, query: KnowledgeQuery) -> tuple[KnowledgePassage, ...]:
        dense_result, sparse_result = await asyncio.gather(
            asyncio.to_thread(
                self._inference.embed,
                self._dense_model,
                [query.text],
                {
                    "input_type": "query",
                    "truncate": "END",
                    "dimension": self._index_dimension,
                },
            ),
            asyncio.to_thread(
                self._inference.embed,
                self._sparse_model,
                [query.text],
                {"input_type": "query", "truncate": "END"},
            ),
        )
        dense_embedding = list(dense_result)[0]
        sparse_embedding = list(sparse_result)[0]
        dense_values = [value * self._alpha for value in _float_values(dense_embedding)]
        sparse_values = _sparse_values(sparse_embedding)
        sparse_values["values"] = [value * (1 - self._alpha) for value in sparse_values["values"]]

        metadata_filter: dict[str, object] = {
            "$and": [
                {"category": {"$eq": query.category.value}},
                {"candidate_ids": {"$in": list(query.candidate_ids)}},
                *({key: {"$eq": value}} for key, value in query.filters.items()),
            ]
        }
        response = await asyncio.to_thread(
            self._index.query,
            top_k=query.top_k,
            vector=dense_values,
            sparse_vector=sparse_values,
            namespace=query.namespace,
            filter=metadata_filter,
            include_metadata=True,
            include_values=False,
            timeout=self._timeout_seconds,
        )
        matches = list(_read(response, "matches", ()))
        documents = [str(_metadata(match).get("text", "")) for match in matches]
        if not documents:
            return ()

        reranked = await asyncio.to_thread(
            self._inference.rerank,
            self._rerank_model,
            query.text,
            documents,
            ["text"],
            False,
            query.rerank_top_n,
        )
        results: list[KnowledgePassage] = []
        requested_candidates = set(query.candidate_ids)
        for item in _read(reranked, "data", ()):
            match_index = int(_read(item, "index", -1))
            if not 0 <= match_index < len(matches):
                continue
            score = max(0.0, min(1.0, float(_read(item, "score", 0.0))))
            match = matches[match_index]
            candidate_ids = _metadata(match).get("candidate_ids")
            if not isinstance(candidate_ids, list):
                continue
            for candidate_id in candidate_ids:
                normalized_id = str(candidate_id)
                if normalized_id not in requested_candidates:
                    continue
                passage = _passage(match, query.namespace, score, normalized_id)
                if passage is not None:
                    results.append(passage)
        return tuple(results)


def _float_values(embedding: object) -> list[float]:
    values = _read(embedding, "values", ())
    return [float(value) for value in values]


def _sparse_values(embedding: object) -> dict[str, list[int] | list[float]]:
    indices = _read(embedding, "sparse_indices", _read(embedding, "indices", ()))
    values = _read(embedding, "sparse_values", _read(embedding, "values", ()))
    return {
        "indices": [int(index) for index in indices],
        "values": [float(value) for value in values],
    }


def _read(value: object, name: str, default: object) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _metadata(match: object) -> Mapping[str, Any]:
    metadata = _read(match, "metadata", {})
    return metadata if isinstance(metadata, Mapping) else {}


def _chunk_metadata(chunk: ContentChunk) -> dict[str, object]:
    return {
        **dict(chunk.metadata),
        "text": chunk.text,
        "source_id": chunk.source_id,
        "category": chunk.category.value,
        "candidate_ids": list(chunk.candidate_ids),
        "title": chunk.title,
        "source_name": chunk.publisher,
        "source_url": chunk.canonical_url,
        "reviewed_at": chunk.reviewed_at.isoformat(),
        "content_version": chunk.content_version,
        "namespace": chunk.namespace,
    }


def _passage(
    match: object,
    namespace: str,
    score: float,
    candidate_id: str,
) -> KnowledgePassage | None:
    metadata = _metadata(match)
    try:
        return KnowledgePassage(
            chunk_id=str(_read(match, "id", "")),
            source_id=str(metadata["source_id"]),
            candidate_id=candidate_id,
            category=Category(str(metadata["category"])),
            text=str(metadata["text"]),
            score=score,
            title=str(metadata["title"]),
            source_name=str(metadata["source_name"]),
            source_url=str(metadata["source_url"]),
            reviewed_at=datetime.fromisoformat(str(metadata["reviewed_at"])),
            content_version=str(metadata["content_version"]),
            namespace=namespace,
        )
    except (KeyError, TypeError, ValueError):
        return None
