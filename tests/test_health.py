"""Operational health probe behavior."""

from pathlib import Path

from advisor_api import create_app
from advisor_api.config import Settings
from advisor_api.container import build_container
from fastapi.testclient import TestClient


class FailingDatabaseProbe:
    async def ping(self) -> None:
        raise RuntimeError("database unavailable")


def test_liveness_and_readiness_are_healthy_in_memory(client: TestClient) -> None:
    for path in ("/health/live", "/health/ready"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["X-API-Version"] == "v1"


def test_readiness_uses_versioned_error_contract_when_database_is_unavailable() -> None:
    app = create_app(
        Settings(_env_file=None, app_env="test", database_mode="memory"),
        container=build_container(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.database_runtime = FailingDatabaseProbe()
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers["X-Error-Contract-Version"] == "v1"


def test_health_routes_are_not_part_of_the_product_openapi(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/health/live" not in paths
    assert "/health/ready" not in paths


def test_bundled_web_shell_and_same_origin_api_alias(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Advisor shell</h1>", encoding="utf-8")
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_mode="memory",
            web_dist_dir=tmp_path,
            enabled_categories="PLANT,DOG",
        )
    )
    with TestClient(app, raise_server_exceptions=False) as web_client:
        shell = web_client.get("/")
        api = web_client.post(
            "/api/v1/recommendations",
            json={
                "category": "DOG",
                "destination": {"zip_code": "30301", "state_code": "GA"},
                "session_id": "7649ff84-05a3-4509-9ae5-62dfaf05d952",
                "questionnaire": {
                    "housing_type": "APARTMENT",
                    "home_size": "SMALL",
                    "rental_allows_pets": False,
                    "outdoor_space": "NONE",
                    "hours_alone": 4,
                    "activity_level": "LOW",
                    "grooming_tolerance": "LOW",
                    "monthly_budget": 200,
                    "children_present": False,
                    "existing_pets": [],
                    "experience": "BEGINNER",
                },
            },
        )

    assert shell.status_code == 200
    assert "Advisor shell" in shell.text
    assert api.status_code == 422
    assert api.json()["error"]["code"] == "NO_ELIGIBLE_CANDIDATES"
