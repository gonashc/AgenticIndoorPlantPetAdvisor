"""Versioned, lossless wrappers for care-plan MCP tool results."""

from typing import Literal

from advisor_api.contracts.base import ContractModel
from advisor_api.contracts.care_plans import CarePlan, CarePlanPreviewResponse
from advisor_api.contracts.errors import ErrorDetail
from pydantic import model_validator

CARE_PLAN_MCP_CONTRACT_VERSION = "v1"


class CarePlanToolError(ContractModel):
    """Known domain failure that the REST facade can reproduce exactly."""

    contract_version: Literal["v1"] = "v1"
    status_code: Literal[404, 409, 422]
    code: str
    message: str
    details: list[ErrorDetail]


class CarePlanToolResult(ContractModel):
    outcome: Literal["success", "error"]
    preview: CarePlanPreviewResponse | None = None
    plan: CarePlan | None = None
    error: CarePlanToolError | None = None

    @model_validator(mode="after")
    def outcome_has_exactly_one_value(self) -> "CarePlanToolResult":
        values = (self.preview, self.plan, self.error)
        if sum(value is not None for value in values) != 1:
            raise ValueError("A care-plan tool result requires exactly one value")
        if self.outcome == "error" and self.error is None:
            raise ValueError("An error outcome requires an error")
        if self.outcome == "success" and self.error is not None:
            raise ValueError("A success outcome cannot contain an error")
        return self
