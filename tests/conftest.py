"""Shared API fixtures."""

from collections.abc import Iterator

import pytest
from advisor_api import create_app
from advisor_api.config import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            openapi_enabled=True,
            langsmith_tracing=False,
            enabled_categories="PLANT,DOG,CAT",
        )
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def plant_payload() -> dict[str, object]:
    return {
        "category": "PLANT",
        "destination": {"zip_code": "10001", "state_code": "NY"},
        "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
        "use_saved_preferences": False,
        "questionnaire": {
            "light_level": "BRIGHT_INDIRECT",
            "humidity": "AVERAGE",
            "indoor_temperature_f": 72,
            "available_space": "MEDIUM",
            "experience": "BEGINNER",
            "watering_availability": "LOW",
            "monthly_budget": 30,
            "children_present": True,
            "pets_present": ["CAT"],
        },
    }
