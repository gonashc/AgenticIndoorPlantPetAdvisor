"""Allowlisted adapter for You.com's current POST search contract."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from services.you_search.credentials import validate_you_api_key


@dataclass(frozen=True, slots=True)
class YouSearchResult:
    title: str
    url: str
    description: str


class YouSearchClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        allowed_source_hosts: frozenset[str] = frozenset(),
        government_only: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = validate_you_api_key(api_key)
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._allowed_hosts = allowed_source_hosts
        self._government_only = government_only
        self._transport = transport

    async def search(self, *, query: str, limit: int) -> Sequence[YouSearchResult]:
        if not query.strip() or len(query) > 500:
            raise ValueError("You.com query must contain between 1 and 500 characters")
        if not 1 <= limit <= 5:
            raise ValueError("You.com result limit must be between 1 and 5")
        request_body: dict[str, object] = {
            "query": query,
            "count": limit,
            "country": "US",
            "language": "EN",
            "safesearch": "moderate",
        }
        if self._allowed_hosts:
            request_body["include_domains"] = sorted(self._allowed_hosts)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                self._base_url,
                headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
                json=request_body,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"You.com search failed with status {response.status_code}")
        payload = response.json()
        return self._parse(payload, limit)

    def _parse(self, payload: object, limit: int) -> tuple[YouSearchResult, ...]:
        if not isinstance(payload, Mapping):
            raise ValueError("You.com returned an invalid response")
        results = payload.get("results")
        if not isinstance(results, Mapping):
            raise ValueError("You.com response is missing results")
        web = results.get("web", [])
        if not isinstance(web, list):
            raise ValueError("You.com web results are invalid")
        parsed: list[YouSearchResult] = []
        for item in web:
            result = self._result(item)
            if result is not None:
                parsed.append(result)
            if len(parsed) == limit:
                break
        return tuple(parsed)

    def _result(self, item: object) -> YouSearchResult | None:
        if not isinstance(item, Mapping):
            return None
        title = item.get("title")
        url = item.get("url")
        description = item.get("description")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            return None
        if not isinstance(description, str) or not description.strip():
            description = self._first_snippet(item.get("snippets"))
        if not description:
            return None
        parsed = urlparse(url)
        host = parsed.hostname.lower() if parsed.hostname else ""
        if parsed.scheme != "https" or not host or not self._is_allowed(host):
            return None
        return YouSearchResult(
            title=title.strip()[:300],
            url=url[:2000],
            description=description.strip()[:1000],
        )

    def _is_allowed(self, host: str) -> bool:
        if self._government_only and not (host.endswith(".gov") or host.endswith(".us")):
            return False
        if not self._allowed_hosts:
            return True
        return any(
            host == allowed or host.endswith(f".{allowed}") for allowed in self._allowed_hosts
        )

    @staticmethod
    def _first_snippet(value: Any) -> str | None:
        if not isinstance(value, list):
            return None
        return next(
            (item.strip() for item in value if isinstance(item, str) and item.strip()), None
        )
