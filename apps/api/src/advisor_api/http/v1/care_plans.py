"""Version 1 care-plan preview, confirmation, and management endpoints."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from advisor_api.container import get_container
from advisor_api.contracts.care_plans import (
    CarePlan,
    CarePlanCreateRequest,
    CarePlanPreviewRequest,
    CarePlanPreviewResponse,
    CarePlanUpdateRequest,
)
from advisor_api.http.auth import authenticated_user
from advisor_api.http.context import request_id
from advisor_api.http.errors import COMMON_ERROR_RESPONSES
from advisor_api.ports.auth import AuthenticatedUser

router = APIRouter(prefix="/care-plans", tags=["care-plans"])
Authenticated = Annotated[AuthenticatedUser, Depends(authenticated_user)]


@router.post(
    "/preview",
    response_model=CarePlanPreviewResponse,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="previewCarePlan",
    summary="Preview a care plan without saving it",
)
async def preview_care_plan(
    payload: CarePlanPreviewRequest,
    request: Request,
    user: Authenticated,
) -> CarePlanPreviewResponse:
    return await get_container(request).care_plans.preview(
        payload, request_id(request), user.owner_id
    )


@router.post(
    "",
    response_model=CarePlan,
    status_code=HTTPStatus.CREATED,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="createCarePlan",
    summary="Persist an explicitly confirmed preview",
)
async def create_care_plan(
    payload: CarePlanCreateRequest,
    request: Request,
    user: Authenticated,
) -> CarePlan:
    return await get_container(request).care_plans.create(
        payload, request_id(request), user.owner_id
    )


@router.get(
    "/{plan_id}",
    response_model=CarePlan,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="getCarePlan",
    summary="Retrieve a saved care plan",
)
async def get_care_plan(
    plan_id: UUID,
    request: Request,
    user: Authenticated,
) -> CarePlan:
    return await get_container(request).care_plans.get(plan_id, user.owner_id, request_id(request))


@router.patch(
    "/{plan_id}",
    response_model=CarePlan,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="updateCarePlan",
    summary="Pause or activate a care plan",
)
async def update_care_plan(
    plan_id: UUID,
    payload: CarePlanUpdateRequest,
    request: Request,
    user: Authenticated,
) -> CarePlan:
    return await get_container(request).care_plans.update(
        plan_id, payload, request_id(request), user.owner_id
    )


@router.post(
    "/{plan_id}/tasks/{task_id}/complete",
    response_model=CarePlan,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="completeCareTask",
    summary="Mark a care task complete",
)
async def complete_care_task(
    plan_id: UUID,
    task_id: UUID,
    request: Request,
    user: Authenticated,
) -> CarePlan:
    return await get_container(request).care_plans.complete_task(
        plan_id, task_id, request_id(request), user.owner_id
    )
