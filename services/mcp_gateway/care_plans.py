"""Authenticated, provider-neutral client for the private Care Plan MCP."""

from typing import Literal
from uuid import UUID

from advisor_api.contracts.care_plans import (
    CarePlan,
    CarePlanCreateRequest,
    CarePlanPreviewRequest,
    CarePlanPreviewResponse,
    CarePlanUpdateRequest,
)
from advisor_api.http.errors import ApiError

from services.care_plan_mcp.contracts import CarePlanToolResult
from services.mcp_gateway.ports import McpToolClient


class CarePlanMcpGateway:
    """Invokes only the approved care-plan tools using the caller's signed assertion."""

    def __init__(
        self,
        client: McpToolClient,
        server_url: str,
        authorization_audience: str,
        *,
        timeout_seconds: float = 8.0,
    ) -> None:
        if not authorization_audience:
            raise ValueError("Care Plan MCP requires a private-service audience")
        self._client = client
        self._server_url = server_url
        self._authorization_audience = authorization_audience
        self._timeout = timeout_seconds

    async def preview(
        self,
        request: CarePlanPreviewRequest,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlanPreviewResponse:
        payload = await self._call(
            "preview_care_plan",
            {**request.model_dump(mode="json"), "request_id": str(request_id)},
            user_assertion,
        )
        return CarePlanPreviewResponse.model_validate(self._success_value(payload, "preview"))

    async def create(
        self,
        request: CarePlanCreateRequest,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        payload = await self._call(
            "create_care_plan",
            {**request.model_dump(mode="json"), "request_id": str(request_id)},
            user_assertion,
        )
        return CarePlan.model_validate(self._success_value(payload, "plan"))

    async def get(
        self,
        plan_id: UUID,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        payload = await self._call(
            "get_care_plan",
            {"plan_id": str(plan_id), "request_id": str(request_id)},
            user_assertion,
        )
        return CarePlan.model_validate(self._success_value(payload, "plan"))

    async def adjust(
        self,
        plan_id: UUID,
        request: CarePlanUpdateRequest,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        payload = await self._call(
            "adjust_care_plan",
            {
                "plan_id": str(plan_id),
                "status": request.status.value,
                "request_id": str(request_id),
            },
            user_assertion,
        )
        return CarePlan.model_validate(self._success_value(payload, "plan"))

    async def complete_task(
        self,
        plan_id: UUID,
        task_id: UUID,
        *,
        request_id: UUID,
        user_assertion: str,
    ) -> CarePlan:
        payload = await self._call(
            "complete_care_task",
            {
                "plan_id": str(plan_id),
                "task_id": str(task_id),
                "request_id": str(request_id),
            },
            user_assertion,
        )
        return CarePlan.model_validate(self._success_value(payload, "plan"))

    async def _call(
        self,
        tool_name: str,
        arguments: dict[str, object],
        user_assertion: str,
    ) -> dict[str, object]:
        payload = await self._client.call_tool(
            server_url=self._server_url,
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=self._timeout,
            authorization_audience=self._authorization_audience,
            forwarded_user_assertion=user_assertion,
        )
        return dict(payload)

    @staticmethod
    def _success_value(payload: dict[str, object], field: Literal["preview", "plan"]) -> object:
        result = CarePlanToolResult.model_validate(payload)
        if result.outcome == "error":
            if result.error is None:
                raise ValueError("Care Plan MCP error result omitted its error envelope")
            raise ApiError(
                result.error.status_code,
                result.error.code,
                result.error.message,
                list(result.error.details),
            )
        value = result.preview if field == "preview" else result.plan
        if value is None:
            raise ValueError(f"Care Plan MCP success result omitted {field}")
        return value
