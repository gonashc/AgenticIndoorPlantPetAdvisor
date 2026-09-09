"""Tests for opt-in, redacted LangSmith recommendation tracing."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from advisor_api import create_app
from advisor_api.config import Settings
from advisor_api.container import build_container
from advisor_api.contracts.base import Category
from advisor_api.observability import langsmith as langsmith_module
from advisor_api.observability.langsmith import build_recommendation_tracer
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_tracing_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="LANGSMITH_API_KEY is required"):
        Settings(
            _env_file=None,
            app_env="test",
            langsmith_tracing=True,
            langsmith_api_key=None,
        )


def test_disabled_tracer_explicitly_disables_ambient_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    @contextmanager
    def fake_tracing_context(**kwargs: object) -> Iterator[None]:
        captured.update(kwargs)
        yield

    monkeypatch.setattr(langsmith_module, "tracing_context", fake_tracing_context)
    tracer = build_recommendation_tracer()

    with tracer.trace(
        request_id=UUID("397dd09d-47c5-4d11-a63a-c8b8a81ff731"),
        category=Category.PLANT,
        transport="http",
    ):
        pass

    assert captured == {"enabled": False}


def test_enabled_tracer_uses_redaction_and_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs

        def close(self, timeout: float | None = None) -> None:
            captured["close_timeout"] = timeout

    @contextmanager
    def fake_tracing_context(**kwargs: object) -> Iterator[None]:
        captured["context"] = kwargs
        yield

    monkeypatch.setattr(langsmith_module, "Client", FakeClient)
    monkeypatch.setattr(langsmith_module, "tracing_context", fake_tracing_context)
    settings = Settings(
        _env_file=None,
        app_env="staging",
        langsmith_tracing=True,
        langsmith_api_key="test-key",
        langsmith_project="advisor-test",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
    )
    tracer = build_recommendation_tracer(settings)
    request_id = UUID("397dd09d-47c5-4d11-a63a-c8b8a81ff731")

    with tracer.trace(
        request_id=request_id,
        category=Category.CAT,
        transport="stream",
    ):
        pass
    tracer.close()

    client_config = captured["client"]
    assert client_config["api_key"] == "test-key"
    assert client_config["hide_inputs"] is True
    assert client_config["hide_outputs"] is True
    context = captured["context"]
    assert context["enabled"] is True
    assert context["project_name"] == "advisor-test"
    assert context["metadata"] == {
        "request_id": str(request_id),
        "environment": "staging",
        "transport": "stream",
        "category": "CAT",
        "api_version": "v1",
        "graph_version": "recommendation-graph-v1",
        "rules_version": "rules-v1",
        "scoring_version": "scoring-v1",
        "prompt_version": "deterministic-explanations-v1",
        "model_version": "none",
        "knowledge_version": "fake-catalog-v1",
    }
    assert "session_id" not in context["metadata"]
    assert captured["close_timeout"] == 5.0


def test_recommendation_endpoints_scope_http_and_stream_traces(
    plant_payload: dict[str, object],
) -> None:
    calls: list[dict[str, object]] = []

    class RecordingTracer:
        @contextmanager
        def trace(self, **kwargs: object) -> Iterator[None]:
            calls.append(dict(kwargs))
            yield

        def close(self) -> None:
            return None

    app = create_app(
        Settings(_env_file=None, app_env="test", langsmith_tracing=False),
        container=build_container(recommendation_tracer=RecordingTracer()),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/v1/recommendations", json=plant_payload)
        with client.stream(
            "POST", "/v1/recommendations/stream", json=plant_payload
        ) as stream_response:
            list(stream_response.iter_lines())

    assert response.status_code == 200
    assert stream_response.status_code == 200
    assert [call["transport"] for call in calls] == ["http", "stream"]
    assert all(call["category"] == Category.PLANT for call in calls)
