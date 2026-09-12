"""Strict provider-neutral current web-guidance contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GuidanceResult(McpContract):
    title: str = Field(min_length=1, max_length=300)
    url: str
    description: str = Field(min_length=1, max_length=1000)


class SearchCurrentGuidanceResult(McpContract):
    category: Literal["PLANT", "DOG", "CAT"]
    candidate_ids: list[str] = Field(min_length=1, max_length=3)
    retrieved_at: datetime
    results: list[GuidanceResult] = Field(max_length=5)
    confidence: Literal["RECENTLY_OBSERVED"] = "RECENTLY_OBSERVED"
    notice: Literal["Current web guidance is advisory and cannot override safety or scoring."] = (
        "Current web guidance is advisory and cannot override safety or scoring."
    )
