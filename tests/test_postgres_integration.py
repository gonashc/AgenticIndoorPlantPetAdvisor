"""Opt-in integration test for a migrated PostgreSQL or Cloud SQL test database."""

import os

import pytest
from advisor_api import create_app
from advisor_api.config import Settings
from fastapi.testclient import TestClient
from pydantic import SecretStr


@pytest.mark.postgres
def test_care_plan_survives_across_requests() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_mode="url",
        database_url=SecretStr(database_url),
    )
    with TestClient(create_app(settings), raise_server_exceptions=True) as client:
        preview = client.post(
            "/v1/care-plans/preview",
            json={
                "session_id": "09ceee83-746f-4ee9-8155-932e743f0ff2",
                "recommendation_id": "integration-plant",
                "category": "PLANT",
                "item_name": "Integration Plant",
                "start_date": "2026-09-05",
                "timezone": "America/New_York",
            },
        ).json()
        created = client.post(
            "/v1/care-plans",
            json={"preview_id": preview["preview_id"], "confirmed": True},
        )
        assert created.status_code == 201
        fetched = client.get(f"/v1/care-plans/{created.json()['plan_id']}")

    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == created.json()["plan_id"]
