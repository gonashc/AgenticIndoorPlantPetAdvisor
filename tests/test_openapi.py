"""Published OpenAPI contract checks."""

import json
from pathlib import Path

from advisor_api import create_app
from fastapi.testclient import TestClient


def test_openapi_is_versioned_and_documents_sse(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["x-api-version"] == "v1"
    assert schema["info"]["x-error-contract-version"] == "v1"
    assert "/v1/recommendations" in schema["paths"]
    assert "/v1/recommendations/stream" in schema["paths"]
    assert "/v1/care-plans/{plan_id}" in schema["paths"]
    stream_schema = schema["paths"]["/v1/recommendations/stream"]["post"]["responses"]["200"][
        "content"
    ]["text/event-stream"]
    assert stream_schema["schema"]["$ref"].endswith("RecommendationStreamEvent")
    assert stream_schema["x-sse"]["resumeHeader"] == "Last-Event-ID"


def test_checked_in_openapi_artifact_matches_application() -> None:
    checked_in = json.loads(
        Path("packages/contracts/openapi/openapi.json").read_text(encoding="utf-8")
    )

    assert checked_in == create_app().openapi()
