"""Strict adoption MCP contracts independent of provider payloads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdoptionSource(McpContract):
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["adoption_listing", "animal_rescue", "animal_shelter"]
    url: str
    distance_miles: float | None = Field(default=None, ge=0)
    verified_at: datetime
    confidence: Literal["RECENTLY_OBSERVED"] = "RECENTLY_OBSERVED"


class FindAdoptionsResult(McpContract):
    sources: list[AdoptionSource] = Field(max_length=3)
