"""Strict wrappers for care-plan MCP tool results."""

from advisor_api.contracts.base import ContractModel
from advisor_api.contracts.care_plans import CarePlan, CarePlanPreviewResponse


class CarePlanPreviewToolResult(ContractModel):
    preview: CarePlanPreviewResponse


class CarePlanToolResult(ContractModel):
    plan: CarePlan
