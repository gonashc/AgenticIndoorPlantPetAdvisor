"""Contract and provider tests for the private climate MCP service."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from mcp import Client
from pydantic import ValidationError

from services.climate_mcp.config import ClimateMcpSettings
from services.climate_mcp.nws import (
    AlertReading,
    ForecastReading,
    NationalWeatherServiceClient,
    WeatherReading,
)
from services.climate_mcp.server import create_server


class StubWeatherProvider:
    async def get_weather(self, *, latitude: float, longitude: float) -> WeatherReading:
        assert latitude == 40.7506
        assert longitude == -73.9972
        now = datetime.now(UTC)
        return WeatherReading(
            forecast=ForecastReading(
                start_time=now,
                end_time=now + timedelta(hours=1),
                temperature=72,
                temperature_unit="F",
                relative_humidity_percent=55,
                wind_speed="5 mph",
                short_forecast="Partly Cloudy",
                source_url="https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly",
            ),
            alerts=(
                AlertReading(
                    event="Heat Advisory",
                    headline="Heat Advisory issued for the area",
                    severity="Moderate",
                    urgency="Expected",
                    effective=now,
                    expires=now + timedelta(hours=4),
                    source_url="https://api.weather.gov/alerts/example",
                ),
            ),
        )


def settings() -> ClimateMcpSettings:
    return ClimateMcpSettings(_env_file=None, app_env="test")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_nws_adapter_follows_trusted_forecast_link_and_fetches_alerts() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert "AgenticIndoorPlantPetAdvisor" in request.headers["User-Agent"]
        if request.url.path.startswith("/points/"):
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "forecastHourly": (
                            "https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly"
                        )
                    }
                },
            )
        if request.url.path.endswith("/forecast/hourly"):
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "periods": [
                            {
                                "startTime": "2026-09-12T04:00:00+00:00",
                                "endTime": "2026-09-12T05:00:00+00:00",
                                "temperature": 72,
                                "temperatureUnit": "F",
                                "relativeHumidity": {"value": 55},
                                "windSpeed": "5 mph",
                                "shortForecast": "Partly Cloudy",
                            }
                        ]
                    }
                },
            )
        assert request.url.path == "/alerts/active"
        assert request.url.params["point"] == "40.7506,-73.9972"
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "id": "https://api.weather.gov/alerts/example",
                        "properties": {
                            "event": "Heat Advisory",
                            "headline": "Heat Advisory issued for the area",
                            "severity": "Moderate",
                            "urgency": "Expected",
                            "effective": "2026-09-12T04:00:00+00:00",
                            "expires": "2026-09-12T08:00:00+00:00",
                        },
                    }
                ]
            },
        )

    provider = NationalWeatherServiceClient(
        base_url="https://api.weather.gov",
        user_agent="AgenticIndoorPlantPetAdvisor/1.0 (https://example.test)",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.get_weather(latitude=40.7506, longitude=-73.9972)

    assert len(calls) == 3
    assert result.forecast.temperature == 72
    assert result.forecast.relative_humidity_percent == 55
    assert result.alerts[0].event == "Heat Advisory"


@pytest.mark.asyncio
async def test_nws_adapter_rejects_untrusted_discovered_forecast_url() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"properties": {"forecastHourly": "https://untrusted.example/forecast"}},
        )

    provider = NationalWeatherServiceClient(
        base_url="https://api.weather.gov",
        user_agent="AgenticIndoorPlantPetAdvisor/1.0 (https://example.test)",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="trusted hourly forecast URL"):
        await provider.get_weather(latitude=40.7506, longitude=-73.9972)


@pytest.mark.asyncio
async def test_climate_mcp_returns_structured_advisory_weather() -> None:
    server = create_server(settings(), StubWeatherProvider())

    async with Client(server) as client:
        result = await client.call_tool(
            "get_weather",
            {"category": "PLANT", "latitude": 40.7506, "longitude": -73.9972},
        )

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["forecast"]["temperature"] == 72
    assert result.structured_content["alerts"][0]["event"] == "Heat Advisory"
    assert "General weather context only" in result.structured_content["advisory"]


@pytest.mark.asyncio
async def test_climate_mcp_rejects_invalid_category_and_coordinates() -> None:
    server = create_server(settings(), StubWeatherProvider())

    async with Client(server) as client:
        category_result = await client.call_tool(
            "get_weather",
            {"category": "BIRD", "latitude": 40.7506, "longitude": -73.9972},
        )
        coordinate_result = await client.call_tool(
            "get_weather",
            {"category": "DOG", "latitude": 100, "longitude": -73.9972},
        )

    assert category_result.is_error
    assert coordinate_result.is_error


def test_production_climate_config_requires_official_nws_api() -> None:
    with pytest.raises(ValidationError, match="official National Weather Service"):
        ClimateMcpSettings(
            _env_file=None,  # type: ignore[call-arg]
            app_env="production",
            nws_base_url="https://weather.example",
        )
