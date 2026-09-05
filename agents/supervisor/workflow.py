"""Hierarchical Supervisor with deterministic category routing."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from advisor_api.contracts.base import (
    Category,
    RequestMetadata,
    ValidationStatus,
    VersionInfo,
)
from advisor_api.contracts.recommendations import (
    RecommendationItem,
    RecommendationResponse,
    SafetyDisclosure,
)
from advisor_api.http.errors import NoEligibleCandidatesError
from advisor_api.ports.data import CatalogRepository
from advisor_api.ports.external_tools import CurrentSourceGateway
from advisor_api.ports.memory import PreferenceMemory
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.cat import build_cat_graph
from agents.dog import build_dog_graph
from agents.evaluator import evaluate
from agents.optimizer import optimize
from agents.plant import build_plant_graph
from services.orchestration.state import RecommendationState
from services.safety import SafetyService
from services.scoring import ScoringService

Graph = CompiledStateGraph[RecommendationState, None, RecommendationState, RecommendationState]


def build_supervisor_graph(
    catalog: CatalogRepository,
    scoring: ScoringService,
    safety: SafetyService,
    source_gateway: CurrentSourceGateway,
    memory: PreferenceMemory,
) -> Graph:
    async def prepare(state: RecommendationState) -> dict[str, object]:
        request = state["request"]
        candidates = await catalog.list_candidates(request.category)
        system_warnings: list[str] = []
        recalled_preferences: Mapping[str, object] = {}
        if request.use_saved_preferences:
            try:
                recalled_preferences = await memory.recall(request.session_id)
            except Exception:
                system_warnings.append(
                    "Saved preferences were unavailable and were not applied to this result."
                )
        return {
            "candidates": tuple(candidates),
            "recalled_preferences": recalled_preferences,
            "repair_attempts": 0,
            "validation_issues": (),
            "system_warnings": tuple(system_warnings),
        }

    def apply_safety(state: RecommendationState) -> dict[str, object]:
        eligible = safety.filter_candidates(state["request"], state["candidates"])
        return {"eligible_candidates": eligible}

    def route_category(
        state: RecommendationState,
    ) -> Literal["plant_specialist", "dog_specialist", "cat_specialist"]:
        category = state["request"].category
        if category == Category.PLANT:
            return "plant_specialist"
        if category == Category.DOG:
            return "dog_specialist"
        return "cat_specialist"

    def next_after_evaluation(
        state: RecommendationState,
    ) -> Literal["optimizer", "compose"]:
        if state.get("validation_issues") and state.get("repair_attempts", 0) < 2:
            return "optimizer"
        return "compose"

    async def compose(state: RecommendationState) -> dict[str, object]:
        ranked = state.get("ranked_candidates", ())
        if not ranked:
            raise NoEligibleCandidatesError(state["request"].category)
        now = datetime.now(UTC)
        items: list[RecommendationItem] = []
        source_lookup_failed = False
        for index, item in enumerate(ranked):
            try:
                local_sources = await source_gateway.find_sources(
                    category=state["request"].category,
                    candidate_id=item.candidate.candidate_id,
                    zip_code=state["request"].destination.zip_code,
                )
            except Exception:
                source_lookup_failed = True
                local_sources = ()
            is_plant = state["request"].category == Category.PLANT
            items.append(
                RecommendationItem(
                    recommendation_id=item.candidate.candidate_id,
                    name=item.candidate.name,
                    scientific_name=item.candidate.scientific_name,
                    profile=item.candidate.profile,
                    score=item.result.score,
                    best_match=index == 0 and item.result.score >= 60,
                    reasons=list(item.result.reasons),
                    concerns=list(item.result.concerns),
                    evidence=list(item.candidate.evidence),
                    local_sources=list(local_sources)[:3],
                    care_summary=list(item.candidate.care_summary),
                    cost=item.candidate.cost,
                    safety=SafetyDisclosure(
                        child_toxicity=(
                            "TOXIC" if item.candidate.toxic_to_children else "NON_TOXIC"
                        )
                        if is_plant
                        else "NOT_APPLICABLE",
                        dog_toxicity=("TOXIC" if item.candidate.toxic_to_dogs else "NON_TOXIC")
                        if is_plant
                        else "NOT_APPLICABLE",
                        cat_toxicity=("TOXIC" if item.candidate.toxic_to_cats else "NON_TOXIC")
                        if is_plant
                        else "NOT_APPLICABLE",
                    ),
                )
            )
        has_live_sources = all(item.local_sources for item in items) and not source_lookup_failed
        warnings = list(state.get("system_warnings", ()))
        if source_lookup_failed:
            warnings.append(
                "Live local-source discovery failed; reviewed catalog results remain available."
            )
        elif not has_live_sources:
            warnings.append(
                "Live local-source discovery is unavailable; results use reviewed fixture data."
            )
        response = RecommendationResponse(
            metadata=RequestMetadata(
                request_id=state["request_id"],
                generated_at=now,
                versions=VersionInfo(),
            ),
            session_id=state["request"].session_id,
            category=state["request"].category,
            recommendations=items,
            validation_status=(
                ValidationStatus.PASSED if has_live_sources else ValidationStatus.DEGRADED
            ),
            warnings=warnings,
        )
        return {"response": response}

    builder: StateGraph[RecommendationState, None, RecommendationState, RecommendationState] = (
        StateGraph(RecommendationState)
    )
    builder.add_node("prepare", prepare)
    builder.add_node("apply_safety", apply_safety)
    builder.add_node("plant_specialist", build_plant_graph(scoring))
    builder.add_node("dog_specialist", build_dog_graph(scoring))
    builder.add_node("cat_specialist", build_cat_graph(scoring))
    builder.add_node("evaluate", evaluate)
    builder.add_node("optimizer", optimize)
    builder.add_node("compose", compose)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "apply_safety")
    builder.add_conditional_edges("apply_safety", route_category)
    builder.add_edge("plant_specialist", "evaluate")
    builder.add_edge("dog_specialist", "evaluate")
    builder.add_edge("cat_specialist", "evaluate")
    builder.add_conditional_edges("evaluate", next_after_evaluation)
    builder.add_edge("optimizer", "evaluate")
    builder.add_edge("compose", END)
    return builder.compile(name="recommendation-supervisor-v1")
