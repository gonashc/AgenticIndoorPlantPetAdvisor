"""Operational health probe behavior."""

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
