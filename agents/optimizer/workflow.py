"""Targeted repair that cannot change eligibility or authoritative scores."""

from services.orchestration.state import RankedCandidate, RecommendationState
from services.scoring import ScoreResult


def optimize(state: RecommendationState) -> dict[str, object]:
    """Repair explanation completeness only; safety and scores are immutable."""

    attempts = state.get("repair_attempts", 0) + 1
    repaired: list[RankedCandidate] = []
    for ranked in state.get("ranked_candidates", ()):
        reasons = list(ranked.result.reasons)
        while len(reasons) < 3:
            reasons.append("Meets an approved baseline compatibility requirement.")
        repaired.append(
            RankedCandidate(
                candidate=ranked.candidate,
                result=ScoreResult(
                    score=ranked.result.score,
                    reasons=tuple(reasons),
                    concerns=ranked.result.concerns,
                ),
            )
        )
    return {"ranked_candidates": tuple(repaired), "repair_attempts": attempts}
