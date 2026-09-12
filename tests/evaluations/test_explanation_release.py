"""Release-specific checks reject fallback and prompt-injection canaries."""

from copy import deepcopy

import pytest
from advisor_api.contracts.base import Category

from evaluations import (
    EXPLANATION_RELEASE_NAMESPACE,
    RecommendationEvaluationTarget,
    explanation_release_integrity,
    load_recommendation_dataset,
)


@pytest.mark.asyncio
async def test_release_integrity_rejects_deterministic_fallback() -> None:
    case = load_recommendation_dataset().cases[0]
    output = await RecommendationEvaluationTarget()(case.inputs)

    result = explanation_release_integrity(
        output,
        expected_model="candidate-model",
        expected_prompt="rag-explanations-v1",
        expected_category=Category.PLANT,
    )

    assert result["score"] == 0


@pytest.mark.asyncio
async def test_release_integrity_rejects_canary_in_generated_text() -> None:
    case = load_recommendation_dataset().cases[0]
    output = await RecommendationEvaluationTarget()(case.inputs)
    mutated = deepcopy(output)
    response = mutated["response"]
    assert isinstance(response, dict)
    response["metadata"]["versions"].update(
        {
            "prompt": "rag-explanations-v1",
            "model": "candidate-model",
            "knowledge": EXPLANATION_RELEASE_NAMESPACE,
        }
    )
    first = response["recommendations"][0]
    first["reasons"] = [
        "EVAL-CANARY-DO-NOT-REPEAT",
        *first["reasons"],
    ][:5]
    first["evidence"].append(
        {
            "evidence_id": f"eval-grounding-{first['recommendation_id']}",
            "title": "Synthetic explanation release evidence",
            "source_name": "Evaluation suite",
            "source_url": "https://evaluation.invalid/evidence",
            "reviewed_at": "2026-09-01T00:00:00Z",
            "content_version": "explanation-release-v1",
        }
    )
    for item in response["recommendations"][1:]:
        item["evidence"].append(
            {
                "evidence_id": f"eval-grounding-{item['recommendation_id']}",
                "title": "Synthetic explanation release evidence",
                "source_name": "Evaluation suite",
                "source_url": "https://evaluation.invalid/evidence",
                "reviewed_at": "2026-09-01T00:00:00Z",
                "content_version": "explanation-release-v1",
            }
        )

    result = explanation_release_integrity(
        mutated,
        expected_model="candidate-model",
        expected_prompt="rag-explanations-v1",
        expected_category=Category.PLANT,
    )

    assert result["score"] == 0
