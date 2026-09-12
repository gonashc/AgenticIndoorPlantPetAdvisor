"""Provider-neutral structured explanation generation boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from advisor_api.contracts.recommendations import RecommendationRequest
from services.retrieval.models import KnowledgePassage

if TYPE_CHECKING:
    from services.orchestration.state import RankedCandidate


@dataclass(frozen=True, slots=True)
class RecommendationNarrative:
    candidate_id: str
    reasons: tuple[str, ...]
    concerns: tuple[str, ...]
    care_summary: tuple[str, ...]
    cited_evidence_ids: tuple[str, ...]


class ExplanationGenerator(Protocol):
    prompt_version: str
    model_version: str

    async def generate(
        self,
        request: RecommendationRequest,
        candidates: Sequence[RankedCandidate],
        passages: Mapping[str, Sequence[KnowledgePassage]],
    ) -> Mapping[str, RecommendationNarrative]: ...


class DeterministicExplanationGenerator:
    prompt_version = "deterministic-explanations-v1"
    model_version = "none"

    async def generate(
        self,
        request: RecommendationRequest,
        candidates: Sequence[RankedCandidate],
        passages: Mapping[str, Sequence[KnowledgePassage]],
    ) -> Mapping[str, RecommendationNarrative]:
        del request, passages
        return {
            ranked.candidate.candidate_id: RecommendationNarrative(
                candidate_id=ranked.candidate.candidate_id,
                reasons=ranked.result.reasons,
                concerns=ranked.result.concerns,
                care_summary=ranked.candidate.care_summary,
                cited_evidence_ids=tuple(
                    evidence.evidence_id for evidence in ranked.candidate.evidence
                ),
            )
            for ranked in candidates
        }
