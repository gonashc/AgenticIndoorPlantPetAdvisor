"""Cat-profile-only ranking subgraph."""

from advisor_api.contracts.base import Category
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.orchestration.ranking import rank_for_category
from services.orchestration.state import RankedCandidate, RecommendationState
from services.scoring import ScoringService

Graph = CompiledStateGraph[RecommendationState, None, RecommendationState, RecommendationState]


def build_cat_graph(scoring: ScoringService) -> Graph:
    def rank(state: RecommendationState) -> dict[str, tuple[RankedCandidate, ...]]:
        return rank_for_category(state, scoring, Category.CAT)

    builder: StateGraph[RecommendationState, None, RecommendationState, RecommendationState] = (
        StateGraph(RecommendationState)
    )
    builder.add_node("rank_cat_profiles", rank)
    builder.add_edge(START, "rank_cat_profiles")
    builder.add_edge("rank_cat_profiles", END)
    return builder.compile(name="cat-specialist-v1")
