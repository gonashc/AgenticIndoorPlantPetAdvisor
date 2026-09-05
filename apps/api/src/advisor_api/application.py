"""FastAPI application composition root."""

from fastapi import FastAPI

from advisor_api.config import Settings
from advisor_api.container import ApplicationContainer, build_container
from advisor_api.http.context import RequestContextMiddleware
from advisor_api.http.errors import register_error_handlers
from advisor_api.http.openapi import configure_openapi
from advisor_api.http.v1 import router as v1_router


def create_app(
    settings: Settings | None = None,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    openapi_url = "/openapi.json" if resolved_settings.openapi_enabled else None
    app = FastAPI(
        title=resolved_settings.app_name,
        version="1.0.0",
        openapi_url=openapi_url,
        docs_url="/docs" if openapi_url else None,
        redoc_url="/redoc" if openapi_url else None,
    )
    app.state.container = container or build_container()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(v1_router)
    configure_openapi(app)
    return app


app = create_app()
