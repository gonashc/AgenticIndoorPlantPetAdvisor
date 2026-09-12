"""Authenticated MCP facade over the existing care-plan application service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast
from uuid import UUID, uuid4

from advisor_api.adapters.auth import GoogleIapTokenVerifier, LocalIdentityTokenVerifier
from advisor_api.contracts.base import Category
from advisor_api.contracts.care_plans import (
    CarePlanCreateRequest,
    CarePlanPreviewRequest,
    CarePlanStatus,
    CarePlanUpdateRequest,
)
from advisor_api.http.errors import ApiError
from advisor_api.ports.auth import IdentityTokenVerifier
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from database.repositories import PostgresCarePlanRepository
from database.runtime import DatabaseRuntime, create_database_runtime
from services.care_plan_mcp.config import CarePlanMcpSettings
from services.care_plan_mcp.contracts import (
    CARE_PLAN_MCP_CONTRACT_VERSION,
    CarePlanToolError,
    CarePlanToolResult,
)
from services.care_plans.service import CarePlanService

CARE_PLAN_SCHEMA_CAPABILITIES = frozenset(
    {
        "care_plan_previews.preview_id",
        "care_plan_previews.owner_id",
        "care_plan_previews.expires_at",
        "care_plan_previews.consumed_at",
        "care_plans.plan_id",
        "care_plans.owner_id",
        "care_plans.status",
        "care_plans.version",
        "care_tasks.task_id",
        "care_tasks.plan_id",
        "care_tasks.completed_at",
    }
)


@dataclass(slots=True)
class CarePlanMcpState:
    care_plans: CarePlanService
    identity_verifier: IdentityTokenVerifier
    database: DatabaseRuntime | None


@dataclass(slots=True)
class RuntimeProbe:
    database: DatabaseRuntime | None = None


def create_server(
    settings: CarePlanMcpSettings | None = None,
    care_plans: CarePlanService | None = None,
    identity_verifier: IdentityTokenVerifier | None = None,
) -> MCPServer[CarePlanMcpState]:
    resolved = settings or CarePlanMcpSettings()
    verifier = identity_verifier or (
        GoogleIapTokenVerifier(resolved.iap_audience)
        if resolved.auth_mode == "google_iap" and resolved.iap_audience
        else LocalIdentityTokenVerifier()
    )
    probe = RuntimeProbe()

    @asynccontextmanager
    async def lifespan(_: MCPServer[CarePlanMcpState]) -> AsyncIterator[CarePlanMcpState]:
        if care_plans is not None:
            yield CarePlanMcpState(
                care_plans=care_plans,
                identity_verifier=verifier,
                database=None,
            )
            return
        runtime = await create_database_runtime(resolved)
        probe.database = runtime
        try:
            await runtime.verify(CARE_PLAN_SCHEMA_CAPABILITIES)
            yield CarePlanMcpState(
                care_plans=CarePlanService(
                    PostgresCarePlanRepository(runtime.session_factory),
                    resolved.enabled_category_values(),
                ),
                identity_verifier=verifier,
                database=runtime,
            )
        finally:
            probe.database = None
            await runtime.close()

    server: MCPServer[CarePlanMcpState] = MCPServer(
        name="advisor-care-plan",
        title="Indoor Plant and Pet Advisor Care Plan Service",
        description=(
            "Previews and performs owner-scoped care-plan actions after verified authentication."
        ),
        version="1.1.0",
        lifespan=lifespan,
    )

    @server.tool(
        name="preview_care_plan",
        description=(
            "Preview deterministic care tasks. The preview is not persisted as an active plan "
            "and still requires explicit confirmation."
        ),
        structured_output=True,
    )
    async def preview_care_plan(
        session_id: UUID,
        recommendation_id: str,
        category: Category,
        item_name: str,
        start_date: date,
        timezone: str,
        ctx: Context[CarePlanMcpState],
        request_id: UUID | None = None,
    ) -> CarePlanToolResult:
        state = ctx.request_context.lifespan_context
        owner_id = await _owner_id(ctx, state.identity_verifier)
        try:
            preview = await state.care_plans.preview(
                CarePlanPreviewRequest(
                    session_id=session_id,
                    recommendation_id=recommendation_id,
                    category=category,
                    item_name=item_name,
                    start_date=start_date,
                    timezone=timezone,
                ),
                request_id or uuid4(),
                owner_id,
            )
        except ApiError as error:
            return _error_result(error)
        return CarePlanToolResult(outcome="success", preview=preview)

    @server.tool(
        name="create_care_plan",
        description=(
            "Persist a previously generated preview only after the user explicitly confirms it."
        ),
        structured_output=True,
    )
    async def create_care_plan(
        preview_id: UUID,
        confirmed: Literal[True],
        ctx: Context[CarePlanMcpState],
        request_id: UUID | None = None,
    ) -> CarePlanToolResult:
        state = ctx.request_context.lifespan_context
        owner_id = await _owner_id(ctx, state.identity_verifier)
        try:
            plan = await state.care_plans.create(
                CarePlanCreateRequest(preview_id=preview_id, confirmed=confirmed),
                request_id or uuid4(),
                owner_id,
            )
        except ApiError as error:
            return _error_result(error)
        return CarePlanToolResult(outcome="success", plan=plan)

    @server.tool(
        name="get_care_plan",
        description="Retrieve an authenticated user's existing care plan.",
        structured_output=True,
    )
    async def get_care_plan(
        plan_id: UUID,
        ctx: Context[CarePlanMcpState],
        request_id: UUID | None = None,
    ) -> CarePlanToolResult:
        state = ctx.request_context.lifespan_context
        owner_id = await _owner_id(ctx, state.identity_verifier)
        try:
            plan = await state.care_plans.get(plan_id, owner_id, request_id or uuid4())
        except ApiError as error:
            return _error_result(error)
        return CarePlanToolResult(outcome="success", plan=plan)

    @server.tool(
        name="adjust_care_plan",
        description="Pause or reactivate an authenticated user's existing care plan.",
        structured_output=True,
    )
    async def adjust_care_plan(
        plan_id: UUID,
        status: CarePlanStatus,
        ctx: Context[CarePlanMcpState],
        request_id: UUID | None = None,
    ) -> CarePlanToolResult:
        state = ctx.request_context.lifespan_context
        owner_id = await _owner_id(ctx, state.identity_verifier)
        try:
            plan = await state.care_plans.update(
                plan_id,
                CarePlanUpdateRequest(status=status),
                request_id or uuid4(),
                owner_id,
            )
        except ApiError as error:
            return _error_result(error)
        return CarePlanToolResult(outcome="success", plan=plan)

    @server.tool(
        name="complete_care_task",
        description="Mark one task complete on an authenticated user's active care plan.",
        structured_output=True,
    )
    async def complete_care_task(
        plan_id: UUID,
        task_id: UUID,
        ctx: Context[CarePlanMcpState],
        request_id: UUID | None = None,
    ) -> CarePlanToolResult:
        state = ctx.request_context.lifespan_context
        owner_id = await _owner_id(ctx, state.identity_verifier)
        try:
            plan = await state.care_plans.complete_task(
                plan_id, task_id, request_id or uuid4(), owner_id
            )
        except ApiError as error:
            return _error_result(error)
        return CarePlanToolResult(outcome="success", plan=plan)

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        if care_plans is not None:
            return JSONResponse(
                {
                    "status": "ok",
                    "service": "advisor-care-plan",
                    "contract_version": CARE_PLAN_MCP_CONTRACT_VERSION,
                }
            )
        if probe.database is None:
            return JSONResponse(
                {
                    "status": "unavailable",
                    "service": "advisor-care-plan",
                    "contract_version": CARE_PLAN_MCP_CONTRACT_VERSION,
                },
                status_code=503,
            )
        try:
            await probe.database.ping()
        except Exception:
            return JSONResponse(
                {
                    "status": "unavailable",
                    "service": "advisor-care-plan",
                    "contract_version": CARE_PLAN_MCP_CONTRACT_VERSION,
                },
                status_code=503,
            )
        return JSONResponse(
            {
                "status": "ok",
                "service": "advisor-care-plan",
                "contract_version": CARE_PLAN_MCP_CONTRACT_VERSION,
            }
        )

    return server


def create_app(settings: CarePlanMcpSettings | None = None) -> Starlette:
    resolved = settings or CarePlanMcpSettings()
    server = create_server(resolved)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=resolved.allowed_hosts(),
        allowed_origins=[],
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=64 * 1024,
        transport_security=security,
        host="0.0.0.0",
    )


async def _owner_id(context: Context[CarePlanMcpState], verifier: IdentityTokenVerifier) -> UUID:
    headers = context.headers or {}
    token = headers.get("x-goog-iap-jwt-assertion") or headers.get("X-Goog-IAP-JWT-Assertion")
    principal = await verifier.verify(token)
    return principal.owner_id


def _error_result(error: ApiError) -> CarePlanToolResult:
    if error.status_code not in {404, 409, 422}:
        raise error
    return CarePlanToolResult(
        outcome="error",
        error=CarePlanToolError(
            status_code=cast(Literal[404, 409, 422], error.status_code),
            code=error.code,
            message=error.message,
            details=error.details,
        ),
    )
