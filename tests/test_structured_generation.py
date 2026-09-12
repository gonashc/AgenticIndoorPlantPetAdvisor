"""Structured LLM explanation boundary tests."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from advisor_api.adapters.in_memory import InMemoryCatalogRepository
from advisor_api.contracts.base import Category, Destination
from advisor_api.contracts.recommendations import PlantQuestionnaire, PlantRecommendationRequest
from langchain_core.language_models.chat_models import BaseChatModel

from agents.structured_generation import LangChainStructuredExplanationAdapter
from services.orchestration.state import RankedCandidate
from services.retrieval.models import KnowledgePassage
from services.scoring import ScoringService


class FakeStructuredRunnable:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output

    async def ainvoke(self, messages: object) -> dict[str, object]:
        del messages
        return self.output


class FakeChatModel:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output

    def with_structured_output(self, schema: object) -> FakeStructuredRunnable:
        del schema
        return FakeStructuredRunnable(self.output)


def request() -> PlantRecommendationRequest:
    return PlantRecommendationRequest(
        category=Category.PLANT,
        destination=Destination(zip_code="10001", state_code="NY"),
        session_id=UUID("c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911"),
        questionnaire=PlantQuestionnaire(
            light_level="BRIGHT_INDIRECT",
            humidity="AVERAGE",
            indoor_temperature_f=72,
            available_space="MEDIUM",
            experience="BEGINNER",
            watering_availability="LOW",
            monthly_budget=30,
            children_present=True,
            pets_present={"CAT"},
        ),
    )


async def ranked_candidate() -> RankedCandidate:
    candidate = (await InMemoryCatalogRepository().list_candidates(Category.PLANT))[0]
    return RankedCandidate(candidate=candidate, result=ScoringService().score(request(), candidate))


def passage() -> KnowledgePassage:
    return KnowledgePassage(
        chunk_id="chunk-spider-care",
        source_id="source-spider",
        candidate_id="plant-spider",
        category=Category.PLANT,
        text="Reviewed guidance for spider plant light and watering.",
        score=0.93,
        title="Spider plant care",
        source_name="Extension service",
        source_url="https://extension.example.edu/spider",
        reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
        content_version="2026-09",
        namespace="knowledge-v1",
    )


@pytest.mark.asyncio
async def test_structured_adapter_accepts_only_supplied_candidates_and_evidence() -> None:
    ranked = await ranked_candidate()
    output: dict[str, object] = {
        "recommendations": [
            {
                "candidate_id": "plant-spider",
                "reasons": ["Safe around cats.", "Fits the light.", "Fits the care routine."],
                "concerns": ["Avoid overwatering."],
                "care_summary": ["Water after the top inch dries."],
                "cited_evidence_ids": ["chunk-spider-care"],
            }
        ]
    }
    adapter = LangChainStructuredExplanationAdapter(
        cast(BaseChatModel, FakeChatModel(output)), model_version="test-model-v1"
    )

    result = await adapter.generate(request(), [ranked], {"plant-spider": [passage()]})

    assert result["plant-spider"].cited_evidence_ids == ("chunk-spider-care",)
    assert result["plant-spider"].reasons[0] == "Safe around cats."


@pytest.mark.asyncio
async def test_structured_adapter_rejects_invented_citations() -> None:
    ranked = await ranked_candidate()
    output: dict[str, object] = {
        "recommendations": [
            {
                "candidate_id": "plant-spider",
                "reasons": ["One", "Two", "Three"],
                "care_summary": ["Carefully."],
                "cited_evidence_ids": ["invented-source"],
            }
        ]
    }
    adapter = LangChainStructuredExplanationAdapter(
        cast(BaseChatModel, FakeChatModel(output)), model_version="test-model-v1"
    )

    with pytest.raises(ValueError, match="outside the supplied context"):
        await adapter.generate(request(), [ranked], {"plant-spider": [passage()]})


@pytest.mark.asyncio
async def test_structured_adapter_requires_retrieved_evidence_for_every_candidate() -> None:
    ranked = await ranked_candidate()
    adapter = LangChainStructuredExplanationAdapter(
        cast(BaseChatModel, FakeChatModel({"recommendations": []})),
        model_version="test-model-v1",
    )

    with pytest.raises(ValueError, match="retrieved evidence per candidate"):
        await adapter.generate(request(), [ranked], {})
