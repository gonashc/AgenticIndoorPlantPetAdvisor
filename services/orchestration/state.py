"""Typed shared state with explicit workflow-owned fields."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from advisor_api.contracts.recommendations import RecommendationRequest, RecommendationResponse
from advisor_api.ports.data import CandidateRecord
from advisor_api.ports.generation import RecommendationNarrative
from typing_extensions import TypedDict

from services.retrieval.models import KnowledgePassage
from services.scoring import ScoreResult


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: CandidateRecord
    result: ScoreResult


class RecommendationState(TypedDict, total=False):
    request: RecommendationRequest
    request_id: UUID
    candidates: tuple[CandidateRecord, ...]
    recalled_preferences: Mapping[str, object]
    eligible_candidates: tuple[CandidateRecord, ...]
    ranked_candidates: tuple[RankedCandidate, ...]
    knowledge_passages: tuple[KnowledgePassage, ...]
    narratives: Mapping[str, RecommendationNarrative]
    explanation_prompt_version: str
    explanation_model_version: str
    validation_issues: tuple[str, ...]
    repair_attempts: int
    system_warnings: tuple[str, ...]
    response: RecommendationResponse
