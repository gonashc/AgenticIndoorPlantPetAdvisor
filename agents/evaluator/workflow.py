"""Deterministic recommendation evaluator."""

from services.orchestration.state import RecommendationState


def evaluate(state: RecommendationState) -> dict[str, tuple[str, ...]]:
    issues: list[str] = []
    ranked = state.get("ranked_candidates", ())
    if not ranked:
        issues.append("NO_ELIGIBLE_CANDIDATES")
    if len(ranked) > 3:
        issues.append("TOO_MANY_RESULTS")
    for item in ranked:
        if len(item.result.reasons) < 3:
            issues.append(f"INSUFFICIENT_REASONS:{item.candidate.candidate_id}")
        if not item.candidate.evidence:
            issues.append(f"MISSING_EVIDENCE:{item.candidate.candidate_id}")
        if not 0 <= item.result.score <= 100:
            issues.append(f"INVALID_SCORE:{item.candidate.candidate_id}")
    return {"validation_issues": tuple(issues)}
