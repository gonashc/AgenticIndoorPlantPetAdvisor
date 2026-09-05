"""OpenAPI metadata and the SSE event schema extension."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import TypeAdapter

from advisor_api.contracts.streaming import RecommendationStreamEvent


def configure_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=(
                "Versioned application API for deterministic Plant, Dog, and Cat "
                "recommendations and explicitly confirmed care plans."
            ),
            routes=app.routes,
            tags=[
                {
                    "name": "recommendations",
                    "description": "Recommendation execution and progress.",
                },
                {"name": "care-plans", "description": "Care-plan preview and confirmed actions."},
            ],
        )
        schema["info"]["x-api-version"] = "v1"
        schema["info"]["x-error-contract-version"] = "v1"
        schema["x-versioning-policy"] = {
            "strategy": "URL major version",
            "current": "v1",
            "breakingChanges": "Require a new major URL prefix",
        }

        event_schema = TypeAdapter(RecommendationStreamEvent).json_schema(
            ref_template="#/components/schemas/{model}"
        )
        definitions = event_schema.pop("$defs", {})
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(definitions)
        components["RecommendationStreamEvent"] = event_schema
        stream_content = schema["paths"]["/v1/recommendations/stream"]["post"]["responses"]["200"][
            "content"
        ]["text/event-stream"]
        stream_content["schema"] = {"$ref": "#/components/schemas/RecommendationStreamEvent"}
        stream_content["x-sse"] = {
            "idField": "event_id",
            "eventField": "event",
            "retryMilliseconds": 3000,
            "resumeHeader": "Last-Event-ID",
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
