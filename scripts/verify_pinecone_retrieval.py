"""Verify live Pinecone hybrid retrieval without exposing provider payloads."""

import argparse
import asyncio

from advisor_api.config import Settings
from advisor_api.contracts.base import Category

from services.retrieval.models import KnowledgeQuery
from services.retrieval.pinecone import PineconeHybridKnowledgeAdapter


async def run(category: Category, candidate_ids: tuple[str, ...], query_text: str) -> int:
    settings = Settings()
    if settings.retrieval_mode != "pinecone":
        raise RuntimeError("Set RETRIEVAL_MODE=pinecone before verification")
    if settings.pinecone_api_key is None or settings.pinecone_index_host is None:
        raise RuntimeError("Pinecone configuration is incomplete")

    adapter = PineconeHybridKnowledgeAdapter(
        api_key=settings.pinecone_api_key.get_secret_value(),
        index_host=settings.pinecone_index_host,
        index_dimension=settings.pinecone_index_dimension,
        dense_model=settings.pinecone_dense_model,
        sparse_model=settings.pinecone_sparse_model,
        rerank_model=settings.pinecone_rerank_model,
        alpha=settings.pinecone_hybrid_alpha,
        timeout_seconds=settings.pinecone_timeout_seconds,
    )
    passages = await adapter.retrieve(
        KnowledgeQuery(
            category=category,
            text=query_text,
            candidate_ids=candidate_ids,
            namespace=settings.pinecone_namespace,
            top_k=8,
            rerank_top_n=5,
        )
    )
    if not passages:
        raise RuntimeError("Pinecone returned no matching approved passages")
    print(
        f"passages={len(passages)} sources={len({item.source_id for item in passages})} "
        f"namespace={settings.pinecone_namespace}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", type=Category, default=Category.PLANT)
    parser.add_argument(
        "--candidate-id",
        action="append",
        dest="candidate_ids",
        default=["plant-spider", "plant-parlor-palm", "plant-boston-fern"],
    )
    parser.add_argument(
        "--query",
        default="pet-safe indoor plant for bright indirect light and low maintenance",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.category, tuple(args.candidate_ids), args.query))


if __name__ == "__main__":
    raise SystemExit(main())
