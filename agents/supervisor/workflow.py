"""Hierarchical Supervisor with deterministic category routing."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from advisor_api.contracts.base import (
    Category,
    EvidenceReference,
    RequestMetadata,
    ValidationStatus,
    VersionInfo,
)
from advisor_api.contracts.recommendations import (
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
    SafetyDisclosure,
)
from advisor_api.http.errors import NoEligibleCandidatesError
from advisor_api.ports.data import CatalogRepository
from advisor_api.ports.external_tools import CurrentSourceGateway
from advisor_api.ports.generation import (
    DeterministicExplanationGenerator,
    ExplanationGenerator,
    RecommendationNarrative,
)
from advisor_api.ports.memory import PreferenceMemory
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.cat import build_cat_graph
from agents.dog import build_dog_graph
from agents.evaluator import evaluate
from agents.optimizer import optimize
from agents.plant import build_plant_graph
from services.orchestration.state import RankedCandidate, RecommendationState
from services.retrieval import EmptyKnowledgeRetriever, KnowledgePassage, KnowledgeQuery
from services.retrieval.ports import KnowledgeRetriever
from services.safety import SafetyService
from services.scoring import ScoringService

Graph = CompiledStateGraph[RecommendationState, None, RecommendationState, RecommendationState]


def build_supervisor_graph(
    catalog: CatalogRepository,
    scoring: ScoringService,
    safety: SafetyService,
    source_gateway: CurrentSourceGateway,
    memory: PreferenceMemory,
    knowledge_retriever: KnowledgeRetriever | None = None,
    explanation_generator: ExplanationGenerator | None = None,
    knowledge_namespace: str = "fake-catalog-v1",
) -> Graph:
    retriever = knowledge_retriever or EmptyKnowledgeRetriever()
    generator = explanation_generator or DeterministicExplanationGenerator()

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

    async def retrieve_knowledge(state: RecommendationState) -> dict[str, object]:
        ranked = state.get("ranked_candidates", ())
        if not ranked:
            return {"knowledge_passages": ()}
        request = state["request"]
        query = KnowledgeQuery(
            category=request.category,
            text=_knowledge_query_text(request),
            candidate_ids=tuple(item.candidate.candidate_id for item in ranked),
            namespace=knowledge_namespace,
        )
        try:
            passages = tuple(await retriever.retrieve(query))
        except Exception:
            warnings = (*state.get("system_warnings", ()), "Approved knowledge retrieval failed.")
            return {"knowledge_passages": (), "system_warnings": warnings}
        return {"knowledge_passages": passages}

    async def generate_explanations(state: RecommendationState) -> dict[str, object]:
        ranked = state.get("ranked_candidates", ())
        grouped = _group_passages(state.get("knowledge_passages", ()))
        try:
            narratives = await generator.generate(state["request"], ranked, grouped)
            return {
                "narratives": narratives,
                "explanation_prompt_version": generator.prompt_version,
                "explanation_model_version": generator.model_version,
            }
        except Exception:
            fallback = DeterministicExplanationGenerator()
            narratives = await fallback.generate(state["request"], ranked, grouped)
            warnings = (
                *state.get("system_warnings", ()),
                "Model-generated explanations were unavailable; "
                "deterministic explanations were used.",
            )
            return {
                "narratives": narratives,
                "system_warnings": warnings,
                "explanation_prompt_version": fallback.prompt_version,
                "explanation_model_version": fallback.model_version,
            }

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
            narrative = state.get("narratives", {}).get(item.candidate.candidate_id)
            if narrative is None:
                narrative = _fallback_narrative(item)
            evidence = _response_evidence(
                item.candidate.evidence,
                state.get("knowledge_passages", ()),
                item.candidate.candidate_id,
                narrative,
            )
            items.append(
                RecommendationItem(
                    recommendation_id=item.candidate.candidate_id,
                    name=item.candidate.name,
                    scientific_name=item.candidate.scientific_name,
                    profile=item.candidate.profile,
                    score=item.result.score,
                    best_match=index == 0 and item.result.score >= 60,
                    reasons=list(narrative.reasons),
                    concerns=list(narrative.concerns),
                    evidence=list(evidence),
                    local_sources=list(local_sources)[:3],
                    care_summary=list(narrative.care_summary),
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
                versions=VersionInfo(
                    prompt=state.get("explanation_prompt_version", generator.prompt_version),
                    model=state.get("explanation_model_version", generator.model_version),
                    knowledge=knowledge_namespace,
                ),
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
    builder.add_node("retrieve_knowledge", retrieve_knowledge)
    builder.add_node("generate_explanations", generate_explanations)
    builder.add_node("evaluate", evaluate)
    builder.add_node("optimizer", optimize)
    builder.add_node("compose", compose)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "apply_safety")
    builder.add_conditional_edges("apply_safety", route_category)
    builder.add_edge("plant_specialist", "retrieve_knowledge")
    builder.add_edge("dog_specialist", "retrieve_knowledge")
    builder.add_edge("cat_specialist", "retrieve_knowledge")
    builder.add_edge("retrieve_knowledge", "generate_explanations")
    builder.add_edge("generate_explanations", "evaluate")
    builder.add_conditional_edges("evaluate", next_after_evaluation)
    builder.add_edge("optimizer", "evaluate")
    builder.add_edge("compose", END)
    return builder.compile(name="recommendation-supervisor-v1")


def _knowledge_query_text(request: RecommendationRequest) -> str:
    values = request.questionnaire.model_dump(mode="json")
    constraints = " ".join(f"{key}={values[key]}" for key in sorted(values))
    return f"{request.category.value} compatibility safety and care {constraints}"


def _group_passages(
    passages: tuple[KnowledgePassage, ...],
) -> dict[str, tuple[KnowledgePassage, ...]]:
    grouped: dict[str, list[KnowledgePassage]] = {}
    for passage in passages:
        grouped.setdefault(passage.candidate_id, []).append(passage)
    return {candidate_id: tuple(items) for candidate_id, items in grouped.items()}


def _fallback_narrative(ranked: RankedCandidate) -> RecommendationNarrative:
    return RecommendationNarrative(
        candidate_id=ranked.candidate.candidate_id,
        reasons=ranked.result.reasons,
        concerns=ranked.result.concerns,
        care_summary=ranked.candidate.care_summary,
        cited_evidence_ids=tuple(evidence.evidence_id for evidence in ranked.candidate.evidence),
    )


def _response_evidence(
    catalog_evidence: tuple[EvidenceReference, ...],
    passages: tuple[KnowledgePassage, ...],
    candidate_id: str,
    narrative: RecommendationNarrative,
) -> tuple[EvidenceReference, ...]:
    evidence_by_id = {evidence.evidence_id: evidence for evidence in catalog_evidence}
    cited = set(narrative.cited_evidence_ids)
    for passage in passages:
        if passage.candidate_id != candidate_id or passage.chunk_id not in cited:
            continue
        evidence_by_id[passage.chunk_id] = EvidenceReference(
            evidence_id=passage.chunk_id,
            title=passage.title,
            source_name=passage.source_name,
            source_url=passage.source_url,
            reviewed_at=passage.reviewed_at,
            content_version=passage.content_version,
        )
    return tuple(evidence_by_id.values())
