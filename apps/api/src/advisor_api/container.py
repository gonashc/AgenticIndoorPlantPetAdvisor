"""Application composition root and request-scoped container access."""

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, cast

from fastapi import Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from advisor_api.adapters.in_memory import (
    EmptyPreferenceMemory,
    InMemoryCarePlanRepository,
    InMemoryCatalogRepository,
    UnavailableCurrentSourceGateway,
    UnavailableLiveContextGateway,
)
from advisor_api.config import Settings
from advisor_api.observability import build_recommendation_tracer
from advisor_api.ports.data import CarePlanRepository, CatalogRepository
from advisor_api.ports.external_tools import CurrentSourceGateway, LiveContextGateway
from advisor_api.ports.generation import DeterministicExplanationGenerator, ExplanationGenerator
from advisor_api.ports.memory import PreferenceMemory
from advisor_api.ports.observability import RecommendationTracer
from advisor_api.ports.traffic import NoopRequestRateLimiter, RequestRateLimiter
from agents.structured_generation import build_openai_explanation_adapter
from agents.supervisor import build_supervisor_graph
from database.repositories import (
    PostgresCarePlanRepository,
    PostgresCatalogRepository,
    PostgresPlantToxicityRepository,
)
from database.runtime import DatabaseRuntime, create_database_runtime
from services.care_plans import CarePlanService
from services.checkpointing import open_postgres_checkpointer
from services.mcp_gateway import (
    CarePlanMcpGateway,
    GoogleCloudRunIdTokenProvider,
    McpCurrentSourceGateway,
    McpLiveContextGateway,
    McpSdkToolClient,
    McpServerConfig,
)
from services.mcp_gateway.ports import McpToolClient
from services.orchestration.service import RecommendationService
from services.retrieval.pinecone import PineconeHybridKnowledgeAdapter
from services.retrieval.ports import KnowledgeRetriever
from services.safety import SafetyService
from services.scoring import ScoringService
from services.traffic_control import (
    RedisCachedMcpToolClient,
    RedisRequestRateLimiter,
    RedisRuntime,
    create_redis_runtime,
)


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    recommendations: RecommendationService
    care_plans: CarePlanService
    care_plan_tools: CarePlanMcpGateway | None
    recommendation_tracer: RecommendationTracer
    rate_limiter: RequestRateLimiter
    resource_stack: AsyncExitStack | None = None

    def close(self) -> None:
        self.recommendation_tracer.close()

    async def aclose(self) -> None:
        if self.resource_stack is not None:
            await self.resource_stack.aclose()
        self.close()


def build_container(
    *,
    catalog: CatalogRepository | None = None,
    care_plan_repository: CarePlanRepository | None = None,
    current_source_gateway: CurrentSourceGateway | None = None,
    live_context_gateway: LiveContextGateway | None = None,
    preference_memory: PreferenceMemory | None = None,
    recommendation_tracer: RecommendationTracer | None = None,
    knowledge_retriever: KnowledgeRetriever | None = None,
    explanation_generator: ExplanationGenerator | None = None,
    safety: SafetyService | None = None,
    care_plan_tools: CarePlanMcpGateway | None = None,
    rate_limiter: RequestRateLimiter | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    resource_stack: AsyncExitStack | None = None,
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
        live_context_gateway or UnavailableLiveContextGateway(),
        knowledge_retriever,
        explanation_generator,
        knowledge_namespace,
        checkpointer,
    )
    tracer = recommendation_tracer or build_recommendation_tracer()
    return ApplicationContainer(
        recommendations=RecommendationService(graph, tracer, enabled_categories),
        care_plans=CarePlanService(resolved_plan_repository, enabled_categories),
        care_plan_tools=care_plan_tools,
        recommendation_tracer=tracer,
        rate_limiter=rate_limiter or NoopRequestRateLimiter(),
        resource_stack=resource_stack,
    )


async def build_configured_container(
    settings: Settings,
) -> tuple[ApplicationContainer, DatabaseRuntime | None]:
    recommendation_tracer = build_recommendation_tracer(settings)
    resource_stack = AsyncExitStack()
    try:
        checkpointer = await _build_checkpointer(settings, resource_stack)
        redis_runtime = await _build_redis_runtime(settings, resource_stack)
        mcp_client, cached_mcp_client = _build_mcp_clients(settings, redis_runtime)
        knowledge_retriever = _build_knowledge_retriever(settings)
        explanation_generator = _build_explanation_generator(settings)
        current_source_gateway = _build_current_source_gateway(settings, cached_mcp_client)
        live_context_gateway = _build_live_context_gateway(settings, cached_mcp_client)
        care_plan_tools = _build_care_plan_gateway(settings, mcp_client)
        rate_limiter = (
            RedisRequestRateLimiter(
                redis_runtime.client,
                limit=settings.rate_limit_requests,
                window_seconds=settings.rate_limit_window_seconds,
            )
            if redis_runtime is not None
            else NoopRequestRateLimiter()
        )
    except Exception:
        await resource_stack.aclose()
        recommendation_tracer.close()
        raise
    if settings.database_mode == "memory":
        return (
            build_container(
                recommendation_tracer=recommendation_tracer,
                knowledge_retriever=knowledge_retriever,
                explanation_generator=explanation_generator,
                current_source_gateway=current_source_gateway,
                live_context_gateway=live_context_gateway,
                care_plan_tools=care_plan_tools,
                rate_limiter=rate_limiter,
                checkpointer=checkpointer,
                resource_stack=resource_stack,
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
        await resource_stack.aclose()
        recommendation_tracer.close()
        raise
    try:
        await runtime.verify()
    except Exception:
        await runtime.close()
        await resource_stack.aclose()
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
            live_context_gateway=live_context_gateway,
            care_plan_tools=care_plan_tools,
            rate_limiter=rate_limiter,
            checkpointer=checkpointer,
            resource_stack=resource_stack,
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
    return build_openai_explanation_adapter(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )


def _build_current_source_gateway(
    settings: Settings, client: McpToolClient
) -> CurrentSourceGateway | None:
    if settings.mcp_mode == "disabled":
        return None
    if settings.mcp_places_url is None and settings.mcp_adoption_url is None:
        return None
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
        client,
        places=places,
        adoption=adoption,
        timeout_seconds=settings.mcp_timeout_seconds,
    )


def _build_care_plan_gateway(
    settings: Settings, client: McpToolClient
) -> CarePlanMcpGateway | None:
    if settings.mcp_mode == "disabled" or settings.mcp_care_plan_url is None:
        return None
    if settings.mcp_auth_mode != "google_cloud_run" or settings.mcp_care_plan_audience is None:
        raise ValueError("Care Plan MCP requires private Cloud Run authentication")
    return CarePlanMcpGateway(
        client,
        settings.mcp_care_plan_url,
        settings.mcp_care_plan_audience,
        timeout_seconds=settings.mcp_timeout_seconds,
    )


def _build_live_context_gateway(
    settings: Settings, client: McpToolClient
) -> McpLiveContextGateway | None:
    if settings.mcp_mode == "disabled":
        return None
    climate = (
        McpServerConfig(
            settings.mcp_climate_url,
            "get_weather_for_zip",
            settings.mcp_climate_audience,
        )
        if settings.mcp_climate_url
        else None
    )
    regulations = (
        McpServerConfig(
            settings.mcp_regulations_url,
            "lookup_pet_regulations",
            settings.mcp_regulations_audience,
        )
        if settings.mcp_regulations_url
        else None
    )
    you = (
        McpServerConfig(
            settings.mcp_you_url,
            "search_current_guidance",
            settings.mcp_you_audience,
        )
        if settings.mcp_you_url
        else None
    )
    if climate is None and regulations is None and you is None:
        return None
    return McpLiveContextGateway(
        client,
        climate=climate,
        regulations=regulations,
        web_guidance=you,
        timeout_seconds=settings.mcp_timeout_seconds,
    )


async def _build_checkpointer(
    settings: Settings, stack: AsyncExitStack
) -> BaseCheckpointSaver[Any] | None:
    if settings.checkpoint_mode == "disabled":
        return None
    if settings.checkpoint_mode == "memory":
        return InMemorySaver(
            serde=JsonPlusSerializer(allowed_msgpack_modules=[("advisor_api",), ("services",)])
        )
    if settings.checkpoint_database_url is None:
        raise ValueError("PostgreSQL checkpoint configuration is incomplete")
    return await stack.enter_async_context(
        open_postgres_checkpointer(settings.checkpoint_database_url.get_secret_value())
    )


async def _build_redis_runtime(settings: Settings, stack: AsyncExitStack) -> RedisRuntime | None:
    if settings.redis_mode == "disabled":
        return None
    if settings.redis_url is None:
        raise ValueError("Redis configuration is incomplete")
    runtime = create_redis_runtime(
        settings.redis_url.get_secret_value(),
        socket_timeout_seconds=settings.redis_socket_timeout_seconds,
    )
    await runtime.verify()
    stack.push_async_callback(runtime.close)
    return runtime


def _build_mcp_clients(
    settings: Settings, redis_runtime: RedisRuntime | None
) -> tuple[McpToolClient, McpToolClient]:
    token_provider = (
        GoogleCloudRunIdTokenProvider() if settings.mcp_auth_mode == "google_cloud_run" else None
    )
    client = McpSdkToolClient(token_provider)
    if redis_runtime is None:
        return client, client
    return (
        client,
        RedisCachedMcpToolClient(
            client,
            redis_runtime.client,
            default_ttl_seconds=settings.mcp_cache_ttl_seconds,
        ),
    )


def get_container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)
