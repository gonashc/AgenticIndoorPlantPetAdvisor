"""Strict provider-neutral contracts for current regulation lookups."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegulationRule(McpContract):
    rule_id: str = Field(min_length=1, max_length=160)
    category: Literal["DOG", "CAT"]
    jurisdiction: str = Field(min_length=1, max_length=160)
    jurisdiction_level: Literal["STATE", "CITY", "COUNTY"]
    topic: Literal[
        "LICENSING",
        "LEASH_OR_RESTRAINT",
        "VACCINATION",
        "ANIMAL_LIMIT",
        "HOUSING",
        "TRAVEL_OR_MOVEMENT",
        "OTHER",
    ]
    summary: str = Field(min_length=1, max_length=1000)
    effective_on: date | None = None
    source_title: str = Field(min_length=1, max_length=300)
    source_url: str
    source_version: str = Field(min_length=1, max_length=100)
    verified_at: datetime
    confidence: Literal["RECENTLY_OBSERVED"] = "RECENTLY_OBSERVED"


class RegulationLookupResult(McpContract):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    category: Literal["DOG", "CAT"]
    state_code: str = Field(pattern=r"^[A-Z]{2}$")
    city: str | None = Field(default=None, max_length=100)
    rules: list[RegulationRule] = Field(max_length=8)
    notice: Literal[
        "Verify current requirements with the cited government authority before acting."
    ] = "Verify current requirements with the cited government authority before acting."
