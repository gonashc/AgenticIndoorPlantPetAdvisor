"""MCP server exposing bounded current U.S. weather context."""

from datetime import UTC, datetime
from typing import Literal, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.climate_mcp.config import ClimateMcpSettings
from services.climate_mcp.contracts import (
    GetWeatherForZipResult,
    GetWeatherResult,
    WeatherAlert,
    WeatherForecast,
)
from services.climate_mcp.geocoding import GoogleZipCoordinateClient, ZipCoordinateProvider
from services.climate_mcp.nws import NationalWeatherServiceClient, WeatherProvider, WeatherReading


def create_server(
    settings: ClimateMcpSettings | None = None,
    provider: WeatherProvider | None = None,
    zip_provider: ZipCoordinateProvider | None = None,
) -> MCPServer[None]:
    resolved = settings or ClimateMcpSettings()
    weather_provider = provider or NationalWeatherServiceClient(
        base_url=resolved.nws_base_url,
        user_agent=resolved.nws_user_agent,
        timeout_seconds=resolved.nws_timeout_seconds,
    )
    coordinate_provider = zip_provider
    if coordinate_provider is None and resolved.zip_coordinate_provider == "google":
        if resolved.google_geocoding_api_key is None:
            raise ValueError("Google ZIP resolver configuration is incomplete")
        coordinate_provider = GoogleZipCoordinateClient(
            api_key=resolved.google_geocoding_api_key.get_secret_value(),
            base_url=resolved.google_geocoding_url,
            timeout_seconds=resolved.google_geocoding_timeout_seconds,
        )
    server: MCPServer[None] = MCPServer(
        name="advisor-climate",
        title="Indoor Plant and Pet Advisor Climate Service",
        description="Returns current NWS forecast context and active alerts for U.S. coordinates.",
        version="1.0.0",
    )

    @server.tool(
        name="get_weather",
        description=(
            "Return current forecast context and up to three active NWS alerts. Output is advisory "
            "and cannot override recommendation safety exclusions or authoritative scoring."
        ),
        structured_output=True,
    )
    async def get_weather(category: str, latitude: float, longitude: float) -> GetWeatherResult:
        if category not in {"PLANT", "DOG", "CAT"}:
            raise ValueError("category must be PLANT, DOG, or CAT")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("latitude or longitude is outside the supported range")
        reading = await weather_provider.get_weather(
            latitude=latitude,
            longitude=longitude,
        )
        return _weather_result(category, latitude, longitude, reading)

    @server.tool(
        name="get_weather_for_zip",
        description=(
            "Resolve one validated U.S. five-digit ZIP through the configured bounded provider, "
            "then return current NWS forecast context and alerts."
        ),
        structured_output=True,
    )
    async def get_weather_for_zip(category: str, zip_code: str) -> GetWeatherForZipResult:
        if category not in {"PLANT", "DOG", "CAT"}:
            raise ValueError("category must be PLANT, DOG, or CAT")
        if coordinate_provider is None:
            raise RuntimeError("ZIP coordinate resolution is unavailable")
        location = await coordinate_provider.resolve(zip_code)
        reading = await weather_provider.get_weather(
            latitude=location.latitude,
            longitude=location.longitude,
        )
        result = _weather_result(category, location.latitude, location.longitude, reading)
        return GetWeatherForZipResult(
            **result.model_dump(),
            zip_code=location.zip_code,
            city=location.city,
            state_code=location.state_code,
        )

    @server.custom_route(  # type: ignore[untyped-decorator]
        "/health", methods=["GET"], include_in_schema=False
    )
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "advisor-climate"})

    return server


def _weather_result(
    category: str,
    latitude: float,
    longitude: float,
    reading: WeatherReading,
) -> GetWeatherResult:
    forecast = reading.forecast
    return GetWeatherResult(
        category=cast(Literal["PLANT", "DOG", "CAT"], category),
        latitude=latitude,
        longitude=longitude,
        retrieved_at=datetime.now(UTC),
        forecast=WeatherForecast(
            start_time=forecast.start_time,
            end_time=forecast.end_time,
            temperature=forecast.temperature,
            temperature_unit=cast(Literal["F", "C"], forecast.temperature_unit),
            relative_humidity_percent=forecast.relative_humidity_percent,
            wind_speed=forecast.wind_speed,
            short_forecast=forecast.short_forecast,
            source_url=forecast.source_url,
        ),
        alerts=[
            WeatherAlert(
                event=alert.event,
                headline=alert.headline,
                severity=alert.severity,
                urgency=alert.urgency,
                effective=alert.effective,
                expires=alert.expires,
                source_url=alert.source_url,
            )
            for alert in reading.alerts
        ],
    )


def create_app(settings: ClimateMcpSettings | None = None) -> Starlette:
    resolved = settings or ClimateMcpSettings()
    server = create_server(resolved)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=resolved.allowed_hosts(),
        allowed_origins=[],
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=64 * 1024,
        transport_security=security,
        host="0.0.0.0",
    )
