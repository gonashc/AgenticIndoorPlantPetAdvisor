"""Discriminated Server-Sent Events for recommendation progress."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from advisor_api.contracts.base import ContractModel
from advisor_api.contracts.errors import ErrorBody
from advisor_api.contracts.recommendations import RecommendationResponse


class ProgressEventBase(ContractModel):
    event_id: str
    sequence: int = Field(ge=1)
    request_id: UUID
    session_id: UUID
    emitted_at: datetime
    schema_version: Literal["v1"] = "v1"


type ProgressStage = Literal[
    "ACCEPTED",
    "VALIDATING",
    "APPLYING_SAFETY",
    "SCORING",
    "EVALUATING",
    "OPTIMIZING",
]


class ProgressData(ContractModel):
    stage: ProgressStage
    percent: int = Field(ge=0, le=99)
    message: str


class RecommendationProgressEvent(ProgressEventBase):
    event: Literal["progress"] = "progress"
    data: ProgressData


class RecommendationCompletedEvent(ProgressEventBase):
    event: Literal["completed"] = "completed"
    data: RecommendationResponse


class RecommendationFailedEvent(ProgressEventBase):
    event: Literal["failed"] = "failed"
    data: ErrorBody


type RecommendationStreamEvent = Annotated[
    RecommendationProgressEvent | RecommendationCompletedEvent | RecommendationFailedEvent,
    Field(discriminator="event"),
]
