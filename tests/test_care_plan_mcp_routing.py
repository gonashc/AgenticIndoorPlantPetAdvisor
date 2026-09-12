"""The public v1 REST contract remains stable when backed by Care Plan MCP."""

from uuid import UUID

from advisor_api import create_app
from advisor_api.adapters.auth import LOCAL_OWNER_ID
from advisor_api.adapters.in_memory import InMemoryCarePlanRepository
from advisor_api.config import Settings
from advisor_api.container import build_container
from advisor_api.contracts.care_plans import (
    CarePlan,
    CarePlanCreateRequest,
    CarePlanPreviewRequest,
    CarePlanPreviewResponse,
    CarePlanUpdateRequest,
)
from fastapi.testclient import TestClient

from services.care_plans import CarePlanService


class InProcessCarePlanGateway:
    def __init__(self) -> None:
        self.service = CarePlanService(
            InMemoryCarePlanRepository(),
            frozenset({"PLANT", "DOG", "CAT"}),
        )
        self.assertions: list[str] = []

    def _record(self, assertion: str) -> None:
        self.assertions.append(assertion)

    async def preview(
        self,
        request: CarePlanPreviewRequest,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlanPreviewResponse:
        self._record(user_assertion)
        return await self.service.preview(request, request_id, LOCAL_OWNER_ID)

    async def create(
        self,
        request: CarePlanCreateRequest,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        self._record(user_assertion)
        return await self.service.create(request, request_id, LOCAL_OWNER_ID)

    async def get(
        self,
        plan_id: UUID,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        self._record(user_assertion)
        return await self.service.get(plan_id, LOCAL_OWNER_ID, request_id)

    async def adjust(
        self,
        plan_id: UUID,
        request: CarePlanUpdateRequest,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        self._record(user_assertion)
        return await self.service.update(plan_id, request, request_id, LOCAL_OWNER_ID)

    async def complete_task(
        self,
        plan_id: UUID,
        task_id: UUID,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        self._record(user_assertion)
        return await self.service.complete_task(plan_id, task_id, request_id, LOCAL_OWNER_ID)


def test_care_plan_rest_lifecycle_routes_through_mcp_without_contract_drift() -> None:
    gateway = InProcessCarePlanGateway()
    container = build_container(care_plan_tools=gateway)  # type: ignore[arg-type]
    app = create_app(
        Settings(_env_file=None, app_env="test", enabled_categories="PLANT,DOG,CAT"),
        container,
    )
    headers = {"X-Goog-IAP-JWT-Assertion": "verified-test-assertion"}

    with TestClient(app, raise_server_exceptions=False) as client:
        preview_response = client.post(
            "/v1/care-plans/preview",
            headers=headers,
            json={
                "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
                "recommendation_id": "cat-calm-adult",
                "category": "CAT",
                "item_name": "Calm Adult Cat Profile",
                "start_date": "2026-09-12",
                "timezone": "America/New_York",
            },
        )
        assert preview_response.status_code == 200
        assert (
            preview_response.json()["metadata"]["request_id"]
            == preview_response.headers["X-Request-ID"]
        )

        created_response = client.post(
            "/v1/care-plans",
            headers=headers,
            json={
                "preview_id": preview_response.json()["preview_id"],
                "confirmed": True,
            },
        )
        assert created_response.status_code == 201
        plan_id = created_response.json()["plan_id"]

        missing_response = client.get(
            "/v1/care-plans/11111111-1111-4111-8111-111111111111",
            headers=headers,
        )
        fetched_response = client.get(f"/v1/care-plans/{plan_id}", headers=headers)

    assert fetched_response.status_code == 200
    assert missing_response.status_code == 404
    assert missing_response.headers["X-Error-Contract-Version"] == "v1"
    assert missing_response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert gateway.assertions == ["verified-test-assertion"] * 4
