"""RAG enrichment integration through the real supervisor graph."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from advisor_api import create_app
from advisor_api.config import Settings
from advisor_api.container import build_container
from advisor_api.contracts.recommendations import RecommendationRequest
from advisor_api.ports.generation import RecommendationNarrative
from fastapi.testclient import TestClient

from services.orchestration.state import RankedCandidate
from services.retrieval.models import KnowledgePassage, KnowledgeQuery


class StubRetriever:
    async def retrieve(self, query: KnowledgeQuery) -> tuple[KnowledgePassage, ...]:
        assert query.category.value == "PLANT"
        assert "plant-spider" in query.candidate_ids
        return (
            KnowledgePassage(
                chunk_id="chunk-spider-reviewed",
                source_id="source-spider-reviewed",
                candidate_id="plant-spider",
                category=query.category,
                text="Spider plants are reviewed as non-toxic to cats.",
                score=0.95,
                title="Spider plant safety",
                source_name="Veterinary reference",
                source_url="https://vet.example.edu/spider-plant",
                reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
                content_version="2026-09",
                namespace=query.namespace,
            ),
        )


class StubGenerator:
    prompt_version = "rag-explanations-v1"
    model_version = "stub-structured-model-v1"

    async def generate(
        self,
        request: RecommendationRequest,
        candidates: Sequence[RankedCandidate],
        passages: Mapping[str, Sequence[KnowledgePassage]],
    ) -> Mapping[str, RecommendationNarrative]:
        del request
        return {
            candidate.candidate.candidate_id: RecommendationNarrative(
                candidate_id=candidate.candidate.candidate_id,
                reasons=(
                    "Passed deterministic household safety constraints.",
                    "Fits the requested light and care capacity.",
                    "Supported by reviewed explanatory evidence.",
                ),
                concerns=candidate.result.concerns,
                care_summary=candidate.candidate.care_summary,
                cited_evidence_ids=tuple(
                    item.chunk_id for item in passages.get(candidate.candidate.candidate_id, ())
                )
                or tuple(item.evidence_id for item in candidate.candidate.evidence),
            )
            for candidate in candidates
        }


class FailingRetriever:
    async def retrieve(self, query: KnowledgeQuery) -> tuple[KnowledgePassage, ...]:
        del query
        raise TimeoutError("vector store unavailable")


class FailingGenerator(StubGenerator):
    async def generate(
        self,
        request: RecommendationRequest,
        candidates: Sequence[RankedCandidate],
        passages: Mapping[str, Sequence[KnowledgePassage]],
    ) -> Mapping[str, RecommendationNarrative]:
        del request, candidates, passages
        raise TimeoutError("model unavailable")


def test_graph_enriches_explanations_without_changing_scores(
    plant_payload: dict[str, object],
) -> None:
    baseline_container = build_container()
    enriched_container = build_container(
        knowledge_retriever=StubRetriever(),
        explanation_generator=StubGenerator(),
        knowledge_namespace="knowledge-candidate-v1",
    )
    settings = Settings(_env_file=None, app_env="test", langsmith_tracing=False)
    with (
        TestClient(create_app(settings, baseline_container)) as baseline_client,
        TestClient(create_app(settings, enriched_container)) as enriched_client,
    ):
        baseline = baseline_client.post("/v1/recommendations", json=plant_payload).json()
        enriched = enriched_client.post("/v1/recommendations", json=plant_payload).json()

    assert [item["score"] for item in enriched["recommendations"]] == [
        item["score"] for item in baseline["recommendations"]
    ]
    spider = next(
        item for item in enriched["recommendations"] if item["recommendation_id"] == "plant-spider"
    )
    assert spider["reasons"][2] == "Supported by reviewed explanatory evidence."
    assert {item["evidence_id"] for item in spider["evidence"]} >= {"chunk-spider-reviewed"}
    assert enriched["metadata"]["versions"] == {
        "api": "v1",
        "graph": "recommendation-graph-v1",
        "rules": "rules-v1",
        "scoring": "scoring-v1",
        "prompt": "rag-explanations-v1",
        "model": "stub-structured-model-v1",
        "knowledge": "knowledge-candidate-v1",
    }


def test_rag_and_model_failures_fall_back_to_deterministic_results(
    plant_payload: dict[str, object],
) -> None:
    container = build_container(
        knowledge_retriever=FailingRetriever(),
        explanation_generator=FailingGenerator(),
        knowledge_namespace="knowledge-candidate-v1",
    )
    settings = Settings(_env_file=None, app_env="test", langsmith_tracing=False)

    with TestClient(create_app(settings, container)) as client:
        response = client.post("/v1/recommendations", json=plant_payload)

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_status"] == "DEGRADED"
    assert "Approved knowledge retrieval failed." in payload["warnings"]
    assert any("deterministic explanations" in warning for warning in payload["warnings"])
    assert all(len(item["reasons"]) >= 3 for item in payload["recommendations"])
    assert payload["metadata"]["versions"]["model"] == "none"
