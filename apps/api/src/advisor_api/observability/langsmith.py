"""LangSmith tracing for recommendation workflows with safe metadata only."""

from contextlib import AbstractContextManager
from uuid import UUID

from langsmith import Client, tracing_context

from advisor_api.config import Settings
from advisor_api.contracts.base import Category, VersionInfo
from advisor_api.ports.observability import RecommendationTracer, TraceTransport


class DisabledRecommendationTracer:
    """Explicitly suppresses ambient LangSmith tracing."""

    def trace(
        self,
        *,
        request_id: UUID,
        category: Category,
        transport: TraceTransport,
    ) -> AbstractContextManager[None]:
        del request_id, category, transport
        return tracing_context(enabled=False)

    def close(self) -> None:
        return None


class LangSmithRecommendationTracer:
    """Scopes LangGraph runs to the configured LangSmith project."""

    def __init__(self, settings: Settings) -> None:
        api_key = settings.langsmith_api_key
        if api_key is None:  # validated by Settings; defensive for type narrowing
            raise ValueError("LangSmith API key is required when tracing is enabled")
        self._client = Client(
            api_url=settings.langsmith_endpoint,
            api_key=api_key.get_secret_value(),
            workspace_id=settings.langsmith_workspace_id,
            hide_inputs=settings.langsmith_hide_inputs,
            hide_outputs=settings.langsmith_hide_outputs,
        )
        self._project = settings.langsmith_project
        self._environment = settings.app_env
        self._api_version = settings.api_version

    def trace(
        self,
        *,
        request_id: UUID,
        category: Category,
        transport: TraceTransport,
    ) -> AbstractContextManager[None]:
        versions = VersionInfo()
        return tracing_context(
            enabled=True,
            client=self._client,
            project_name=self._project,
            tags=[
                f"environment:{self._environment}",
                f"api:{self._api_version}",
                f"category:{category.value.lower()}",
                f"transport:{transport}",
            ],
            metadata={
                "request_id": str(request_id),
                "environment": self._environment,
                "transport": transport,
                "category": category.value,
                "api_version": self._api_version,
                "graph_version": versions.graph,
                "rules_version": versions.rules,
                "scoring_version": versions.scoring,
                "prompt_version": versions.prompt,
                "model_version": versions.model,
                "knowledge_version": versions.knowledge,
            },
        )

    def close(self) -> None:
        self._client.close(timeout=5.0)


def build_recommendation_tracer(settings: Settings | None = None) -> RecommendationTracer:
    if settings is None or not settings.langsmith_tracing:
        return DisabledRecommendationTracer()
    return LangSmithRecommendationTracer(settings)
