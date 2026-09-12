"""Application composition root and request-scoped container access."""

from dataclasses import dataclass
from typing import cast

from fastapi import Request

from advisor_api.adapters.in_memory import (
    EmptyPreferenceMemory,
    InMemoryCarePlanRepository,
    InMemoryCatalogRepository,
    UnavailableCurrentSourceGateway,
)
from advisor_api.config import Settings
from advisor_api.observability import build_recommendation_tracer
from advisor_api.ports.data import CarePlanRepository, CatalogRepository
from advisor_api.ports.external_tools import CurrentSourceGateway
from advisor_api.ports.generation import DeterministicExplanationGenerator, ExplanationGenerator
from advisor_api.ports.memory import PreferenceMemory
from advisor_api.ports.observability import RecommendationTracer
from agents.structured_generation import LangChainStructuredExplanationAdapter
from agents.supervisor import build_supervisor_graph
from database.repositories import (
    PostgresCarePlanRepository,
    PostgresCatalogRepository,
    PostgresPlantToxicityRepository,
)
from database.runtime import DatabaseRuntime, create_database_runtime
from services.care_plans import CarePlanService
from services.mcp_gateway import (
    CarePlanMcpGateway,
    GoogleCloudRunIdTokenProvider,
    McpCurrentSourceGateway,
    McpSdkToolClient,
    McpServerConfig,
)
from services.orchestration.service import RecommendationService
from services.retrieval.pinecone import PineconeHybridKnowledgeAdapter
from services.retrieval.ports import KnowledgeRetriever
from services.safety import SafetyService
from services.scoring import ScoringService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    recommendations: RecommendationService
    care_plans: CarePlanService
    care_plan_tools: CarePlanMcpGateway | None
    recommendation_tracer: RecommendationTracer

    def close(self) -> None:
        self.recommendation_tracer.close()


def build_container(
    *,
    catalog: CatalogRepository | None = None,
    care_plan_repository: CarePlanRepository | None = None,
    current_source_gateway: CurrentSourceGateway | None = None,
    preference_memory: PreferenceMemory | None = None,
    recommendation_tracer: RecommendationTracer | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
    explanation_generator: ExplanationGenerator | None = None,
    safety: SafetyService | None = None,
    care_plan_tools: CarePlanMcpGateway | None = None,
    enabled_categories: frozenset[str] = frozenset({"PLANT", "DOG", "CAT"}),
    knowledge_namespace: str = "fake-catalog-v1",
) -> ApplicationContainer:
    resolved_catalog = catalog or InMemoryCatalogRepository()
    resolved_plan_repository = care_plan_repository or InMemoryCarePlanRepository()
    scoring = ScoringService()
    resolved_safety = safety or SafetyService()
    graph = build_supervisor_graph(
        resolved_catalog,
        scoring,
        resolved_safety,
        current_source_gateway or UnavailableCurrentSourceGateway(),
        preference_memory or EmptyPreferenceMemory(),
        knowledge_retriever,
        explanation_generator,
        knowledge_namespace,
    )
    tracer = recommendation_tracer or build_recommendation_tracer()
    return ApplicationContainer(
        recommendations=RecommendationService(graph, tracer, enabled_categories),
        care_plans=CarePlanService(resolved_plan_repository, enabled_categories),
        care_plan_tools=care_plan_tools,
        recommendation_tracer=tracer,
    )


async def build_configured_container(
    settings: Settings,
) -> tuple[ApplicationContainer, DatabaseRuntime | None]:
    recommendation_tracer = build_recommendation_tracer(settings)
    knowledge_retriever = _build_knowledge_retriever(settings)
    explanation_generator = _build_explanation_generator(settings)
    current_source_gateway = _build_current_source_gateway(settings)
    care_plan_tools = _build_care_plan_gateway(settings)
    if settings.database_mode == "memory":
        return (
            build_container(
                recommendation_tracer=recommendation_tracer,
                knowledge_retriever=knowledge_retriever,
                explanation_generator=explanation_generator,
                current_source_gateway=current_source_gateway,
                care_plan_tools=care_plan_tools,
                enabled_categories=settings.enabled_category_values(),
                knowledge_namespace=(
                    settings.pinecone_namespace
                    if knowledge_retriever is not None
                    else "fake-catalog-v1"
                ),
            ),
            None,
        )
    try:
        runtime = await create_database_runtime(settings)
    except Exception:
        recommendation_tracer.close()
        raise
    try:
        await runtime.verify()
    except Exception:
        await runtime.close()
        recommendation_tracer.close()
        raise
    return (
        build_container(
            catalog=PostgresCatalogRepository(runtime.session_factory),
            care_plan_repository=PostgresCarePlanRepository(runtime.session_factory),
            recommendation_tracer=recommendation_tracer,
            knowledge_retriever=knowledge_retriever,
            explanation_generator=explanation_generator,
            current_source_gateway=current_source_gateway,
            care_plan_tools=care_plan_tools,
            safety=SafetyService(
                PostgresPlantToxicityRepository(
                    runtime.session_factory,
                    allowed_trust_tiers=(
                        frozenset({"AUTHORITATIVE", "EXPERT_REVIEWED"})
                        if settings.app_env == "production"
                        else frozenset({"AUTHORITATIVE", "EXPERT_REVIEWED", "DEMO_UNVERIFIED"})
                    ),
                )
            ),
            enabled_categories=settings.enabled_category_values(),
            knowledge_namespace=(
                settings.pinecone_namespace
                if knowledge_retriever is not None
                else "fake-catalog-v1"
            ),
        ),
        runtime,
    )


def _build_knowledge_retriever(settings: Settings) -> KnowledgeRetriever | None:
    if settings.retrieval_mode == "disabled":
        return None
    if settings.pinecone_api_key is None or settings.pinecone_index_host is None:
        raise ValueError("Pinecone configuration is incomplete")
    return PineconeHybridKnowledgeAdapter(
        api_key=settings.pinecone_api_key.get_secret_value(),
        index_host=settings.pinecone_index_host,
        index_dimension=settings.pinecone_index_dimension,
        dense_model=settings.pinecone_dense_model,
        sparse_model=settings.pinecone_sparse_model,
        rerank_model=settings.pinecone_rerank_model,
        alpha=settings.pinecone_hybrid_alpha,
        timeout_seconds=settings.pinecone_timeout_seconds,
    )


def _build_explanation_generator(settings: Settings) -> ExplanationGenerator:
    if settings.explanation_mode == "deterministic":
        return DeterministicExplanationGenerator()
    if settings.openai_api_key is None or settings.openai_model is None:
        raise ValueError("OpenAI explanation configuration is incomplete")
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=0,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        store=False,
    )
    return LangChainStructuredExplanationAdapter(model, model_version=settings.openai_model)


def _build_current_source_gateway(settings: Settings) -> CurrentSourceGateway | None:
    if settings.mcp_mode == "disabled":
        return None
    if settings.mcp_places_url is None and settings.mcp_adoption_url is None:
        return None
    token_provider = (
        GoogleCloudRunIdTokenProvider() if settings.mcp_auth_mode == "google_cloud_run" else None
    )
    places = (
        McpServerConfig(
            settings.mcp_places_url,
            "find_places",
            settings.mcp_places_audience,
        )
        if settings.mcp_places_url
        else None
    )
    adoption = (
        McpServerConfig(
            settings.mcp_adoption_url,
            "find_adoptions",
            settings.mcp_adoption_audience,
        )
        if settings.mcp_adoption_url
        else None
    )
    return McpCurrentSourceGateway(
        McpSdkToolClient(token_provider),
        places=places,
        adoption=adoption,
        timeout_seconds=settings.mcp_timeout_seconds,
    )


def _build_care_plan_gateway(settings: Settings) -> CarePlanMcpGateway | None:
    if settings.mcp_mode == "disabled" or settings.mcp_care_plan_url is None:
        return None
    if settings.mcp_auth_mode != "google_cloud_run" or settings.mcp_care_plan_audience is None:
        raise ValueError("Care Plan MCP requires private Cloud Run authentication")
    return CarePlanMcpGateway(
        McpSdkToolClient(GoogleCloudRunIdTokenProvider()),
        settings.mcp_care_plan_url,
        settings.mcp_care_plan_audience,
        timeout_seconds=settings.mcp_timeout_seconds,
    )


def get_container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)
