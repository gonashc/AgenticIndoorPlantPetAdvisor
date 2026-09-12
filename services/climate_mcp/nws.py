"""National Weather Service adapter hidden behind the climate MCP contract."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True, slots=True)
class ForecastReading:
    start_time: datetime
    end_time: datetime
    temperature: float
    temperature_unit: str
    relative_humidity_percent: float | None
    wind_speed: str | None
    short_forecast: str
    source_url: str


@dataclass(frozen=True, slots=True)
class AlertReading:
    event: str
    headline: str
    severity: str
    urgency: str
    effective: datetime | None
    expires: datetime | None
    source_url: str


@dataclass(frozen=True, slots=True)
class WeatherReading:
    forecast: ForecastReading
    alerts: Sequence[AlertReading]


class WeatherProvider(Protocol):
    async def get_weather(self, *, latitude: float, longitude: float) -> WeatherReading: ...


class NationalWeatherServiceClient:
    """Read-only forecast and active-alert client for U.S. coordinates."""

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._transport = transport

    async def get_weather(self, *, latitude: float, longitude: float) -> WeatherReading:
        point = f"{latitude:.4f},{longitude:.4f}"
        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            headers={"User-Agent": self._user_agent, "Accept": "application/geo+json"},
        ) as client:
            points_payload = await self._get_json(client, f"{self._base_url}/points/{point}")
            points_properties = self._properties(points_payload, "points")
            forecast_url = self._trusted_nws_url(points_properties.get("forecastHourly"))
            if forecast_url is None:
                raise ValueError("NWS points response is missing a trusted hourly forecast URL")
            forecast_payload, alerts_payload = await asyncio.gather(
                self._get_json(client, forecast_url),
                self._get_json(client, f"{self._base_url}/alerts/active", params={"point": point}),
            )
        return WeatherReading(
            forecast=self._parse_forecast(forecast_payload, forecast_url),
            alerts=self._parse_alerts(alerts_payload),
        )

    @staticmethod
    async def _get_json(
        client: httpx.AsyncClient,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        response = await client.get(url, params=params)
        if response.status_code >= 400:
            raise RuntimeError(f"NWS request failed with status {response.status_code}")
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("NWS returned an invalid response")
        return payload

    @staticmethod
    def _properties(payload: Mapping[str, Any], resource: str) -> Mapping[str, Any]:
        properties = payload.get("properties")
        if not isinstance(properties, Mapping):
            raise ValueError(f"NWS {resource} response is missing properties")
        return properties

    def _parse_forecast(self, payload: Mapping[str, Any], source_url: str) -> ForecastReading:
        properties = self._properties(payload, "forecast")
        periods = properties.get("periods")
        if not isinstance(periods, list) or not periods or not isinstance(periods[0], Mapping):
            raise ValueError("NWS forecast response is missing hourly periods")
        period = periods[0]
        start_time = self._datetime(period.get("startTime"), "forecast startTime")
        end_time = self._datetime(period.get("endTime"), "forecast endTime")
        temperature = period.get("temperature")
        unit = period.get("temperatureUnit")
        short_forecast = period.get("shortForecast")
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            raise ValueError("NWS forecast temperature is invalid")
        if unit not in {"F", "C"}:
            raise ValueError("NWS forecast temperature unit is invalid")
        if not isinstance(short_forecast, str) or not short_forecast.strip():
            raise ValueError("NWS short forecast is missing")
        humidity = self._humidity(period.get("relativeHumidity"))
        wind_speed = period.get("windSpeed")
        return ForecastReading(
            start_time=start_time,
            end_time=end_time,
            temperature=float(temperature),
            temperature_unit=unit,
            relative_humidity_percent=humidity,
            wind_speed=wind_speed.strip()[:80] if isinstance(wind_speed, str) else None,
            short_forecast=short_forecast.strip()[:300],
            source_url=source_url,
        )

    def _parse_alerts(self, payload: Mapping[str, Any]) -> tuple[AlertReading, ...]:
        features = payload.get("features", [])
        if not isinstance(features, list):
            raise ValueError("NWS alerts response is missing features")
        alerts: list[AlertReading] = []
        for feature in features:
            alert = self._parse_alert(feature)
            if alert is not None:
                alerts.append(alert)
            if len(alerts) == 3:
                break
        return tuple(alerts)

    def _parse_alert(self, feature: Any) -> AlertReading | None:
        if not isinstance(feature, Mapping):
            return None
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            return None
        event = properties.get("event")
        headline = properties.get("headline")
        severity = properties.get("severity")
        urgency = properties.get("urgency")
        source_url = self._trusted_nws_url(feature.get("id") or properties.get("@id"))
        if not isinstance(event, str) or not event.strip():
            return None
        if not isinstance(headline, str) or not headline.strip():
            return None
        if not isinstance(severity, str) or not severity.strip():
            return None
        if not isinstance(urgency, str) or not urgency.strip():
            return None
        if source_url is None:
            return None
        return AlertReading(
            event=event.strip()[:120],
            headline=headline.strip()[:500],
            severity=severity.strip()[:40],
            urgency=urgency.strip()[:40],
            effective=self._optional_datetime(properties.get("effective")),
            expires=self._optional_datetime(properties.get("expires")),
            source_url=source_url,
        )

    @staticmethod
    def _humidity(value: Any) -> float | None:
        if not isinstance(value, Mapping):
            return None
        raw = value.get("value")
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            return None
        humidity = float(raw)
        return humidity if 0 <= humidity <= 100 else None

    @staticmethod
    def _datetime(value: Any, field: str) -> datetime:
        parsed = NationalWeatherServiceClient._optional_datetime(value)
        if parsed is None:
            raise ValueError(f"NWS {field} is invalid")
        return parsed

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None

    @staticmethod
    def _trusted_nws_url(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or parsed.hostname != "api.weather.gov":
            return None
        return value.strip()
