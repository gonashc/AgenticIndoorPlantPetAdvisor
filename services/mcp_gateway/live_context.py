"""Bounded MCP enrichment that cannot change deterministic recommendation decisions."""

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from advisor_api.contracts.base import Category
from advisor_api.contracts.recommendations import AdvisorySource, LiveAdvisory
from advisor_api.ports.external_tools import LiveContextResult

from services.mcp_gateway.gateway import McpServerConfig
from services.mcp_gateway.ports import McpToolClient


class McpLiveContextGateway:
    """Calls only approved advisory tools after ranking has completed."""

    def __init__(
        self,
        client: McpToolClient,
        *,
        climate: McpServerConfig | None = None,
        regulations: McpServerConfig | None = None,
        web_guidance: McpServerConfig | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        expected = (
            (climate, "get_weather_for_zip"),
            (regulations, "lookup_pet_regulations"),
            (web_guidance, "search_current_guidance"),
        )
        if not any(config is not None for config, _ in expected):
            raise ValueError("At least one live-context MCP server must be configured")
        if any(config is not None and config.tool_name != tool for config, tool in expected):
            raise ValueError("Live-context gateway accepts only approved advisory tools")
        self._client = client
        self._climate = climate
        self._regulations = regulations
        self._web_guidance = web_guidance
        self._timeout = timeout_seconds

    async def enrich(
        self,
        *,
        category: Category,
        candidate_ids: Sequence[str],
        zip_code: str,
        state_code: str | None,
    ) -> LiveContextResult:
        advisories: list[LiveAdvisory] = []
        warnings: list[str] = []
        city: str | None = None
        resolved_state = state_code

        if self._climate is not None:
            try:
                climate_payload = await self._call(
                    self._climate,
                    {"category": category.value, "zip_code": zip_code},
                )
                advisories.extend(self._climate_advisories(climate_payload))
                city = self._optional_text(climate_payload.get("city"), 100)
                resolved_state = self._state_code(climate_payload.get("state_code")) or state_code
            except Exception:
                warnings.append("Current climate context was unavailable.")

        calls: list[tuple[str, asyncio.Task[Mapping[str, object]]]] = []
        if self._regulations is not None and category in {Category.DOG, Category.CAT}:
            if resolved_state is None:
                warnings.append("Current regulation context requires a state code.")
            else:
                calls.append(
                    (
                        "regulations",
                        asyncio.create_task(
                            self._call(
                                self._regulations,
                                {
                                    "category": category.value,
                                    "state_code": resolved_state,
                                    "city": city,
                                    "limit": 5,
                                },
                            )
                        ),
                    )
                )
        if self._web_guidance is not None:
            calls.append(
                (
                    "web guidance",
                    asyncio.create_task(
                        self._call(
                            self._web_guidance,
                            {
                                "category": category.value,
                                "candidate_ids": list(candidate_ids[:3]),
                                "state_code": resolved_state,
                                "limit": 3,
                            },
                        )
                    ),
                )
            )

        for label, task in calls:
            try:
                payload = await task
                if label == "regulations":
                    advisories.extend(self._regulation_advisories(payload))
                else:
                    advisories.extend(self._web_advisories(payload))
            except Exception:
                warnings.append(f"Current {label} was unavailable.")
        return LiveContextResult(tuple(advisories[:12]), tuple(warnings))

    async def _call(
        self, config: McpServerConfig, arguments: Mapping[str, object]
    ) -> Mapping[str, object]:
        return await self._client.call_tool(
            server_url=config.url,
            tool_name=config.tool_name,
            arguments=arguments,
            timeout_seconds=self._timeout,
            authorization_audience=config.authorization_audience,
        )

    @classmethod
    def _climate_advisories(cls, payload: Mapping[str, object]) -> tuple[LiveAdvisory, ...]:
        forecast = cls._mapping(payload.get("forecast"), "climate forecast")
        source = cls._source(
            "National Weather Service hourly forecast",
            forecast.get("source_url"),
            payload.get("retrieved_at"),
        )
        temperature = forecast.get("temperature")
        unit = forecast.get("temperature_unit")
        short = cls._required_text(forecast.get("short_forecast"), 300)
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            raise ValueError("Climate temperature is invalid")
        if unit not in {"F", "C"}:
            raise ValueError("Climate temperature unit is invalid")
        advisories = [
            LiveAdvisory(
                kind="CLIMATE",
                title="Current climate context",
                summary=f"{float(temperature):g}°{unit}; {short}. Advisory context only.",
                sources=[source],
            )
        ]
        alerts = payload.get("alerts", [])
        if not isinstance(alerts, list):
            raise ValueError("Climate alerts must be a list")
        for value in alerts[:3]:
            alert = cls._mapping(value, "climate alert")
            advisories.append(
                LiveAdvisory(
                    kind="CLIMATE",
                    title=cls._required_text(alert.get("event"), 120),
                    summary=cls._required_text(alert.get("headline"), 500),
                    sources=[
                        cls._source(
                            "National Weather Service alert",
                            alert.get("source_url"),
                            payload.get("retrieved_at"),
                        )
                    ],
                )
            )
        return tuple(advisories)

    @classmethod
    def _regulation_advisories(cls, payload: Mapping[str, object]) -> tuple[LiveAdvisory, ...]:
        verified_at = payload.get("retrieved_at")
        advisories: list[LiveAdvisory] = []
        rules = payload.get("rules", [])
        sources = payload.get("discovery_sources", [])
        if not isinstance(rules, list) or not isinstance(sources, list):
            raise ValueError("Regulation MCP returned invalid collections")
        for value in rules[:5]:
            rule = cls._mapping(value, "regulation rule")
            advisories.append(
                LiveAdvisory(
                    kind="REGULATION",
                    title=cls._required_text(rule.get("source_title"), 300)[:160],
                    summary=cls._required_text(rule.get("summary"), 1000),
                    sources=[
                        cls._source(
                            cls._required_text(rule.get("source_title"), 300),
                            rule.get("source_url"),
                            rule.get("verified_at") or verified_at,
                        )
                    ],
                )
            )
        for value in sources[: 5 - len(advisories)]:
            source_value = cls._mapping(value, "regulation discovery source")
            title = cls._required_text(source_value.get("title"), 300)
            advisories.append(
                LiveAdvisory(
                    kind="REGULATION",
                    title=title[:160],
                    summary=(
                        cls._required_text(source_value.get("description"), 800)
                        + " Verify the requirement with the cited authority before acting."
                    )[:1000],
                    sources=[
                        cls._source(
                            title,
                            source_value.get("url"),
                            source_value.get("verified_at") or verified_at,
                        )
                    ],
                )
            )
        return tuple(advisories)

    @classmethod
    def _web_advisories(cls, payload: Mapping[str, object]) -> tuple[LiveAdvisory, ...]:
        retrieved_at = payload.get("retrieved_at")
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Web guidance results must be a list")
        advisories: list[LiveAdvisory] = []
        for value in results[:5]:
            result = cls._mapping(value, "web guidance result")
            title = cls._required_text(result.get("title"), 300)
            advisories.append(
                LiveAdvisory(
                    kind="WEB_GUIDANCE",
                    title=title[:160],
                    summary=cls._required_text(result.get("description"), 1000),
                    sources=[cls._source(title, result.get("url"), retrieved_at)],
                )
            )
        return tuple(advisories)

    @staticmethod
    def _mapping(value: object, name: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be an object")
        return value

    @staticmethod
    def _required_text(value: object, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("MCP text value is missing")
        return value.strip()[:max_length]

    @classmethod
    def _optional_text(cls, value: object, max_length: int) -> str | None:
        if value is None:
            return None
        return cls._required_text(value, max_length)

    @staticmethod
    def _state_code(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().upper()
        return normalized if len(normalized) == 2 and normalized.isalpha() else None

    @classmethod
    def _source(cls, title: str, url_value: object, timestamp: object) -> AdvisorySource:
        url = cls._required_text(url_value, 2000)
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Live advisory sources must use HTTPS")
        verified_at = cls._datetime(timestamp)
        return AdvisorySource(title=title, url=url, verified_at=verified_at)

    @staticmethod
    def _datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("Live advisory timestamp is missing")
        if parsed.tzinfo is None or parsed > datetime.now(UTC):
            raise ValueError("Live advisory timestamp is invalid")
        return parsed
