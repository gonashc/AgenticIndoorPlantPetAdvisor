"""Care-plan request and response contracts."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from advisor_api.contracts.base import Category, ContractModel, RequestMetadata


class Cadence(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"


class CarePlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class CareTask(ContractModel):
    task_id: UUID
    title: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=500)
    cadence: Cadence
    next_due_on: date
    completed_at: datetime | None = None


class CarePlanPreviewRequest(ContractModel):
    session_id: UUID
    recommendation_id: str = Field(min_length=1, max_length=100)
    category: Category
    item_name: str = Field(min_length=1, max_length=120)
    start_date: date
    timezone: str = Field(pattern=r"^[A-Za-z_]+(?:/[A-Za-z0-9_+\-]+)+$")


class CarePlanPreviewResponse(ContractModel):
    metadata: RequestMetadata
    preview_id: UUID
    expires_at: datetime
    session_id: UUID
    recommendation_id: str
    category: Category
    item_name: str
    timezone: str
    tasks: list[CareTask] = Field(min_length=1)
    confirmation_required: Literal[True] = True


class CarePlanCreateRequest(ContractModel):
    preview_id: UUID
    confirmed: Literal[True]


class CarePlanUpdateRequest(ContractModel):
    status: CarePlanStatus


class CarePlan(ContractModel):
    metadata: RequestMetadata
    plan_id: UUID
    session_id: UUID
    recommendation_id: str
    category: Category
    item_name: str
    timezone: str
    status: CarePlanStatus
    tasks: list[CareTask] = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
