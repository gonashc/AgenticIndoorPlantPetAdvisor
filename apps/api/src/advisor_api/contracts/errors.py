"""Stable public error contract."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from advisor_api.contracts.base import ContractModel


class ErrorDetail(ContractModel):
    field: str | None = None
    code: str
    message: str


class ErrorBody(ContractModel):
    code: str
    message: str
    request_id: UUID
    details: list[ErrorDetail] = Field(default_factory=list)
    contract_version: Literal["v1"] = "v1"


class ErrorEnvelope(ContractModel):
    error: ErrorBody
