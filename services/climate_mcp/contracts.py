"""Strict provider-neutral contracts for current weather context."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WeatherForecast(McpContract):
    start_time: datetime
    end_time: datetime
    temperature: float
    temperature_unit: Literal["F", "C"]
    relative_humidity_percent: float | None = Field(default=None, ge=0, le=100)
    wind_speed: str | None = Field(default=None, max_length=80)
    short_forecast: str = Field(min_length=1, max_length=300)
    source_url: str


class WeatherAlert(McpContract):
    event: str = Field(min_length=1, max_length=120)
    headline: str = Field(min_length=1, max_length=500)
    severity: str = Field(min_length=1, max_length=40)
    urgency: str = Field(min_length=1, max_length=40)
    effective: datetime | None = None
    expires: datetime | None = None
    source_url: str


class GetWeatherResult(McpContract):
    category: Literal["PLANT", "DOG", "CAT"]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    retrieved_at: datetime
    confidence: Literal["RECENTLY_OBSERVED"] = "RECENTLY_OBSERVED"
    forecast: WeatherForecast
    alerts: list[WeatherAlert] = Field(max_length=3)
    advisory: Literal[
        "General weather context only; follow National Weather Service and local authorities."
    ] = "General weather context only; follow National Weather Service and local authorities."
