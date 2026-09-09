"""CI regression gate for the source-controlled recommendation dataset."""

from copy import deepcopy
from typing import Any

import pytest

from evaluations import (
    RECOMMENDATION_EVALUATORS,
    RecommendationEvaluationTarget,
    load_recommendation_dataset,
)
from evaluations.recommendations import RecommendationEvaluationCase

DATASET = load_recommendation_dataset()


@pytest.fixture(scope="module")
def evaluation_target() -> RecommendationEvaluationTarget:
    return RecommendationEvaluationTarget()


@pytest.mark.evaluation
@pytest.mark.asyncio
@pytest.mark.parametrize("case", DATASET.cases, ids=lambda case: case.case_id)
async def test_recommendation_case_passes_all_evaluators(
    case: RecommendationEvaluationCase,
    evaluation_target: RecommendationEvaluationTarget,
) -> None:
    outputs = await evaluation_target(case.inputs)
    references = case.reference_outputs.model_dump(mode="json")

    results = [evaluator(outputs, references) for evaluator in RECOMMENDATION_EVALUATORS]

    assert all(result["score"] == 1 for result in results), results


@pytest.mark.evaluation
@pytest.mark.asyncio
async def test_recommendation_dataset_is_repeatable(
    evaluation_target: RecommendationEvaluationTarget,
) -> None:
    for case in DATASET.cases:
        first = await evaluation_target(case.inputs)
        second = await evaluation_target(case.inputs)

        assert _without_volatile_metadata(first) == _without_volatile_metadata(second)


def test_recommendation_dataset_is_synthetic_and_covers_all_categories() -> None:
    assert len(DATASET.cases) >= 5
    assert {case.metadata["category"] for case in DATASET.cases} == {"PLANT", "DOG", "CAT"}
    assert all(case.metadata["source"] == "synthetic" for case in DATASET.cases)


def _without_volatile_metadata(output: dict[str, object]) -> dict[str, object]:
    canonical: dict[str, Any] = deepcopy(output)
    response = canonical.get("response")
    if isinstance(response, dict):
        metadata = response.get("metadata")
        if isinstance(metadata, dict):
            metadata.pop("generated_at", None)
    return canonical
