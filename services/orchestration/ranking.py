"""Selected-specialist ranking operation."""

from advisor_api.contracts.base import Category

from services.orchestration.state import RankedCandidate, RecommendationState
from services.scoring import ScoringService


def rank_for_category(
    state: RecommendationState,
    scoring: ScoringService,
    category: Category,
) -> dict[str, tuple[RankedCandidate, ...]]:
    request = state["request"]
    if request.category != category:
        raise ValueError(f"{category} specialist received {request.category} state")
    ranked = tuple(
        sorted(
            (
                RankedCandidate(candidate=candidate, result=scoring.score(request, candidate))
                for candidate in state["eligible_candidates"]
            ),
            key=lambda item: (-item.result.score, item.candidate.candidate_id),
        )[:3]
    )
    return {"ranked_candidates": ranked}
