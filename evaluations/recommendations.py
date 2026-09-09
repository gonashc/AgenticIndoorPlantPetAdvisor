"""Deterministic offline evaluators for the v1 recommendation workflow."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from advisor_api.container import ApplicationContainer, build_container
from advisor_api.contracts.base import Category, VersionInfo
from advisor_api.contracts.recommendations import RecommendationRequest, RecommendationResponse
from advisor_api.http.errors import ApiError
from pydantic import BaseModel, Field, TypeAdapter, model_validator

DATASET_PATH = Path(__file__).parent / "datasets" / "recommendation_v1.json"
REQUEST_ADAPTER: TypeAdapter[RecommendationRequest] = TypeAdapter(RecommendationRequest)


class RecommendationReference(BaseModel):
    """Expected behavior used by deterministic recommendation evaluators."""

    expected_status: Literal["success", "error"]
    expected_category: Category | None = None
    expected_error_code: str | None = None
    forbidden_recommendation_ids: list[str] = Field(default_factory=list)
    required_recommendation_ids: list[str] = Field(default_factory=list)
    expected_ranking: list[str] = Field(default_factory=list)
    required_safety: dict[str, bool | str] = Field(default_factory=dict)
    min_results: int = Field(default=1, ge=1, le=3)
    max_results: int = Field(default=3, ge=1, le=3)
    expected_versions: VersionInfo = Field(default_factory=VersionInfo)

    @model_validator(mode="after")
    def expected_outcome_is_complete(self) -> "RecommendationReference":
        if self.expected_status == "success" and self.expected_category is None:
            raise ValueError("Successful cases require expected_category")
        if self.expected_status == "error" and not self.expected_error_code:
            raise ValueError("Error cases require expected_error_code")
        if self.min_results > self.max_results:
            raise ValueError("min_results cannot exceed max_results")
        return self


class RecommendationEvaluationCase(BaseModel):
    """One synthetic dataset example and its reference behavior."""

    case_id: str = Field(pattern=r"^[a-z0-9-]+$")
    inputs: dict[str, object]
    reference_outputs: RecommendationReference
    metadata: dict[str, str] = Field(default_factory=dict)


class RecommendationEvaluationDataset(BaseModel):
    """Versioned, source-controlled recommendation evaluation dataset."""

    name: str
    description: str
    version: str
    cases: list[RecommendationEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> "RecommendationEvaluationDataset":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Evaluation case IDs must be unique")
        return self


class RecommendationEvaluationOutput(BaseModel):
    """Stable target output shared by local and LangSmith evaluation runs."""

    status: Literal["success", "error"]
    response: RecommendationResponse | None = None
    error_code: str | None = None


class RecommendationEvaluationTarget:
    """Invokes the real recommendation service for an evaluation example."""

    def __init__(self, container: ApplicationContainer | None = None) -> None:
        self._container = container or build_container()

    async def __call__(self, inputs: dict[str, object]) -> dict[str, object]:
        request_data = inputs.get("request")
        request = REQUEST_ADAPTER.validate_python(request_data)
        request_id = uuid5(NAMESPACE_URL, f"advisor-eval:{request.session_id}")
        try:
            response = await self._container.recommendations.recommend(request, request_id)
        except ApiError as exc:
            return RecommendationEvaluationOutput(
                status="error",
                error_code=exc.code,
            ).model_dump(mode="json")
        return RecommendationEvaluationOutput(
            status="success",
            response=response,
        ).model_dump(mode="json")


def load_recommendation_dataset(
    path: Path = DATASET_PATH,
) -> RecommendationEvaluationDataset:
    return RecommendationEvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def outcome_correctness(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, object]:
    actual = RecommendationEvaluationOutput.model_validate(outputs)
    expected = RecommendationReference.model_validate(reference_outputs)
    if actual.status != expected.expected_status:
        return _score("outcome_correctness", False, "Success/error outcome did not match.")
    if actual.status == "error":
        passed = actual.error_code == expected.expected_error_code
        return _score("outcome_correctness", passed, "Compared the expected error code.")
    passed = actual.response is not None and actual.response.category == expected.expected_category
    return _score("outcome_correctness", passed, "Compared the routed response category.")


def hard_constraint_safety(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, object]:
    actual = RecommendationEvaluationOutput.model_validate(outputs)
    expected = RecommendationReference.model_validate(reference_outputs)
    if actual.status == "error":
        passed = (
            expected.expected_status == "error"
            and actual.error_code == expected.expected_error_code
        )
        return _score("hard_constraint_safety", passed, "Validated the expected hard rejection.")
    if actual.response is None:
        return _score("hard_constraint_safety", False, "Successful output had no response.")

    recommendations = actual.response.recommendations
    recommendation_ids = {item.recommendation_id for item in recommendations}
    forbidden = recommendation_ids.intersection(expected.forbidden_recommendation_ids)
    missing = set(expected.required_recommendation_ids).difference(recommendation_ids)
    safety_matches = all(
        getattr(item.safety, field, None) == required_value
        for item in recommendations
        for field, required_value in expected.required_safety.items()
    )
    passed = not forbidden and not missing and safety_matches
    comment = f"forbidden={sorted(forbidden)}, missing_required={sorted(missing)}"
    return _score("hard_constraint_safety", passed, comment)


def response_quality(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, object]:
    actual = RecommendationEvaluationOutput.model_validate(outputs)
    expected = RecommendationReference.model_validate(reference_outputs)
    if actual.status == "error":
        passed = expected.expected_status == "error"
        return _score("response_quality", passed, "Not applicable to an expected rejection.")
    if actual.response is None:
        return _score("response_quality", False, "Successful output had no response.")

    recommendations = actual.response.recommendations
    passed = (
        expected.min_results <= len(recommendations) <= expected.max_results
        and all(len(item.reasons) >= 3 for item in recommendations)
        and all(item.evidence for item in recommendations)
        and all(item.care_summary for item in recommendations)
        and all(item.safety.hard_constraints_passed for item in recommendations)
        and all(0 <= item.score <= 100 for item in recommendations)
    )
    return _score(
        "response_quality",
        passed,
        "Checked result count, reasons, evidence, care summary, safety, and score bounds.",
    )


def ranking_consistency(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, object]:
    actual = RecommendationEvaluationOutput.model_validate(outputs)
    expected = RecommendationReference.model_validate(reference_outputs)
    if actual.status == "error":
        passed = expected.expected_status == "error"
        return _score("ranking_consistency", passed, "Not applicable to an expected rejection.")
    if actual.response is None:
        return _score("ranking_consistency", False, "Successful output had no response.")

    recommendations = actual.response.recommendations
    scores = [item.score for item in recommendations]
    identifiers = [item.recommendation_id for item in recommendations]
    expected_ranking_matches = (
        not expected.expected_ranking or identifiers == expected.expected_ranking
    )
    best_match_positions = [index for index, item in enumerate(recommendations) if item.best_match]
    best_match_valid = not best_match_positions or best_match_positions == [0]
    passed = (
        scores == sorted(scores, reverse=True) and expected_ranking_matches and best_match_valid
    )
    return _score("ranking_consistency", passed, f"Observed ranking: {identifiers}")


def provenance_complete(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, object]:
    actual = RecommendationEvaluationOutput.model_validate(outputs)
    expected = RecommendationReference.model_validate(reference_outputs)
    if actual.status == "error":
        passed = expected.expected_status == "error"
        return _score("provenance_complete", passed, "Not applicable to an expected rejection.")
    if actual.response is None:
        return _score("provenance_complete", False, "Successful output had no response.")
    passed = actual.response.metadata.versions == expected.expected_versions
    return _score("provenance_complete", passed, "Compared all reconstructability versions.")


def _score(key: str, passed: bool, comment: str) -> dict[str, object]:
    return {"key": key, "score": int(passed), "comment": comment}


RecommendationEvaluator = Callable[
    [dict[str, Any], dict[str, Any]],
    dict[str, object],
]

RECOMMENDATION_EVALUATORS: tuple[RecommendationEvaluator, ...] = (
    outcome_correctness,
    hard_constraint_safety,
    response_quality,
    ranking_consistency,
    provenance_complete,
)
