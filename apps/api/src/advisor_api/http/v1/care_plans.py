"""Version 1 care-plan preview, confirmation, and management endpoints."""

from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter, Request

from advisor_api.container import get_container
from advisor_api.contracts.care_plans import (
    CarePlan,
    CarePlanCreateRequest,
    CarePlanPreviewRequest,
    CarePlanPreviewResponse,
    CarePlanUpdateRequest,
)
from advisor_api.http.context import request_id
from advisor_api.http.errors import COMMON_ERROR_RESPONSES

router = APIRouter(prefix="/care-plans", tags=["care-plans"])


@router.post(
    "/preview",
    response_model=CarePlanPreviewResponse,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="previewCarePlan",
    summary="Preview a care plan without saving it",
)
def preview_care_plan(
    payload: CarePlanPreviewRequest,
    request: Request,
) -> CarePlanPreviewResponse:
    return get_container(request).care_plans.preview(payload, request_id(request))


@router.post(
    "",
    response_model=CarePlan,
    status_code=HTTPStatus.CREATED,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="createCarePlan",
    summary="Persist an explicitly confirmed preview",
)
async def create_care_plan(payload: CarePlanCreateRequest, request: Request) -> CarePlan:
    return await get_container(request).care_plans.create(payload, request_id(request))


@router.get(
    "/{plan_id}",
    response_model=CarePlan,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="getCarePlan",
    summary="Retrieve a saved care plan",
)
async def get_care_plan(plan_id: UUID, request: Request) -> CarePlan:
    return await get_container(request).care_plans.get(plan_id, request_id(request))


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
) -> CarePlan:
    return await get_container(request).care_plans.update(plan_id, payload, request_id(request))


@router.post(
    "/{plan_id}/tasks/{task_id}/complete",
    response_model=CarePlan,
    responses=COMMON_ERROR_RESPONSES,
    operation_id="completeCareTask",
    summary="Mark a care task complete",
)
async def complete_care_task(plan_id: UUID, task_id: UUID, request: Request) -> CarePlan:
    return await get_container(request).care_plans.complete_task(
        plan_id, task_id, request_id(request)
    )
