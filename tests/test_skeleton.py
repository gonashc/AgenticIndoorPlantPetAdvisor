"""Guardrails for the intentionally route-free skeleton."""

from advisor_api import create_app
from advisor_api.config import Settings


def test_skeleton_publishes_no_routes() -> None:
    app = create_app(Settings(app_env="test"))

    assert app.routes == []
    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None
