"""FastAPI application factory for the pre-contract skeleton."""

from fastapi import FastAPI

from advisor_api.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an intentionally route-free application.

    OpenAPI and interactive documentation stay disabled until the v1 contract is
    approved. Router registration is deliberately deferred to the implementation
    phase requested by the user.
    """

    resolved_settings = settings or Settings()
    return FastAPI(
        title=resolved_settings.app_name,
        version="0.0.0-skeleton",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
