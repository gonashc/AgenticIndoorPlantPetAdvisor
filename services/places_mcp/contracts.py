"""Strict MCP tool contracts independent of the Google Places payload."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlantLocationSource(McpContract):
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["plant_nursery"] = "plant_nursery"
    url: str
    distance_miles: float | None = Field(default=None, ge=0)
    verified_at: datetime
    confidence: Literal["RECENTLY_OBSERVED"] = "RECENTLY_OBSERVED"


class FindPlacesResult(McpContract):
    sources: list[PlantLocationSource] = Field(max_length=3)
