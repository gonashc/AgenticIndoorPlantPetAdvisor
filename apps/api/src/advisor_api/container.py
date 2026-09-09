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
from advisor_api.ports.memory import PreferenceMemory
from advisor_api.ports.observability import RecommendationTracer
from agents.supervisor import build_supervisor_graph
from database.repositories import PostgresCarePlanRepository, PostgresCatalogRepository
from database.runtime import DatabaseRuntime, create_database_runtime
from services.care_plans import CarePlanService
from services.orchestration.service import RecommendationService
from services.safety import SafetyService
from services.scoring import ScoringService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    recommendations: RecommendationService
    care_plans: CarePlanService
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
) -> ApplicationContainer:
    resolved_catalog = catalog or InMemoryCatalogRepository()
    resolved_plan_repository = care_plan_repository or InMemoryCarePlanRepository()
    scoring = ScoringService()
    safety = SafetyService()
    graph = build_supervisor_graph(
        resolved_catalog,
        scoring,
        safety,
        current_source_gateway or UnavailableCurrentSourceGateway(),
        preference_memory or EmptyPreferenceMemory(),
    )
    tracer = recommendation_tracer or build_recommendation_tracer()
    return ApplicationContainer(
        recommendations=RecommendationService(graph, tracer),
        care_plans=CarePlanService(resolved_plan_repository),
        recommendation_tracer=tracer,
    )


async def build_configured_container(
    settings: Settings,
) -> tuple[ApplicationContainer, DatabaseRuntime | None]:
    recommendation_tracer = build_recommendation_tracer(settings)
    if settings.database_mode == "memory":
        return build_container(recommendation_tracer=recommendation_tracer), None
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
        ),
        runtime,
    )


def get_container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)
