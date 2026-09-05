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
from advisor_api.ports.data import CarePlanRepository, CatalogRepository
from advisor_api.ports.external_tools import CurrentSourceGateway
from advisor_api.ports.memory import PreferenceMemory
from agents.supervisor import build_supervisor_graph
from services.care_plans import CarePlanService
from services.orchestration.service import RecommendationService
from services.safety import SafetyService
from services.scoring import ScoringService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    recommendations: RecommendationService
    care_plans: CarePlanService


def build_container(
    *,
    catalog: CatalogRepository | None = None,
    care_plan_repository: CarePlanRepository | None = None,
    current_source_gateway: CurrentSourceGateway | None = None,
    preference_memory: PreferenceMemory | None = None,
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
    return ApplicationContainer(
        recommendations=RecommendationService(graph),
        care_plans=CarePlanService(resolved_plan_repository),
    )


def get_container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)
