"""FastAPI application composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from advisor_api.config import Settings
from advisor_api.container import ApplicationContainer, build_configured_container
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

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database_runtime = None
        if container is not None:
            application.state.container = container
        else:
            configured_container, database_runtime = await build_configured_container(
                resolved_settings
            )
            application.state.container = configured_container
        try:
            yield
        finally:
            if database_runtime is not None:
                await database_runtime.close()

    app = FastAPI(
        title=resolved_settings.app_name,
        version="1.0.0",
        openapi_url=openapi_url,
        docs_url="/docs" if openapi_url else None,
        redoc_url="/redoc" if openapi_url else None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(v1_router)
    configure_openapi(app)
    return app


app = create_app()
