"""Durable LangGraph checkpoint integration tests."""

import os
from uuid import UUID, uuid4

import pytest
from advisor_api.config import Settings
from advisor_api.container import build_configured_container
from advisor_api.contracts.recommendations import PlantRecommendationRequest
from fastapi.testclient import TestClient
from pydantic import SecretStr


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_postgres_checkpointer_persists_a_completed_recommendation() -> None:
    asyncpg_url = os.getenv("TEST_DATABASE_URL")
    if not asyncpg_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    checkpoint_url = asyncpg_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    settings = Settings(
        _env_file=None,
        app_env="test",
        checkpoint_mode="postgres",
        checkpoint_database_url=SecretStr(checkpoint_url),
    )
    container, runtime = await build_configured_container(settings)
    assert runtime is None
    request = PlantRecommendationRequest.model_validate(
        {
            "category": "PLANT",
            "destination": {"zip_code": "10001", "state_code": "NY"},
            "session_id": str(uuid4()),
            "questionnaire": {
                "light_level": "BRIGHT_INDIRECT",
                "humidity": "AVERAGE",
                "indoor_temperature_f": 72,
                "available_space": "MEDIUM",
                "experience": "BEGINNER",
                "watering_availability": "LOW",
                "monthly_budget": 30,
                "children_present": False,
                "pets_present": [],
            },
        }
    )
    request_id = uuid4()
    owner_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    try:
        response = await container.recommendations.recommend(request, request_id, owner_id)
        state = await container.recommendations._graph.aget_state(  # noqa: SLF001
            container.recommendations._graph_config(request_id, owner_id)  # noqa: SLF001
        )
    finally:
        await container.aclose()

    assert response.recommendations
    assert state.values["response"].metadata.request_id == request_id


def test_checkpoint_thread_ids_are_opaque_and_owner_isolated() -> None:
    from services.orchestration.service import RecommendationService

    request_id = uuid4()
    first = RecommendationService._graph_config(  # noqa: SLF001
        request_id, UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    )
    second = RecommendationService._graph_config(  # noqa: SLF001
        request_id, UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    )

    assert first["configurable"]["thread_id"] != second["configurable"]["thread_id"]
    assert str(request_id) not in first["configurable"]["thread_id"]


def test_strict_checkpoint_serializer_supports_recommendation_state() -> None:
    from advisor_api import create_app

    app = create_app(Settings(_env_file=None, app_env="test", checkpoint_mode="memory"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/recommendations",
            headers={"X-Request-ID": str(uuid4())},
            json={
                "category": "PLANT",
                "destination": {"zip_code": "10001", "state_code": "NY"},
                "session_id": str(uuid4()),
                "questionnaire": {
                    "light_level": "BRIGHT_INDIRECT",
                    "humidity": "AVERAGE",
                    "indoor_temperature_f": 72,
                    "available_space": "MEDIUM",
                    "experience": "BEGINNER",
                    "watering_availability": "LOW",
                    "monthly_budget": 30,
                    "children_present": False,
                    "pets_present": [],
                },
            },
        )

    assert response.status_code == 200
