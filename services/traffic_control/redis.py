"""Fail-closed rate limits and fail-open caching over one Redis connection pool."""

import hashlib
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from advisor_api.ports.traffic import RateLimitDependencyUnavailable, RateLimitExceeded
from redis.asyncio import Redis
from redis.exceptions import RedisError

from services.mcp_gateway.ports import McpToolClient

_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
"""


@dataclass(slots=True)
class RedisRuntime:
    client: Redis

    async def verify(self) -> None:
        await self.client.ping()

    async def close(self) -> None:
        await self.client.aclose()


def create_redis_runtime(url: str, *, socket_timeout_seconds: float) -> RedisRuntime:
    client: Redis = Redis.from_url(
        url,
        decode_responses=False,
        socket_connect_timeout=socket_timeout_seconds,
        socket_timeout=socket_timeout_seconds,
        health_check_interval=30,
    )
    return RedisRuntime(client)


class RedisRequestRateLimiter:
    """Atomic fixed-window limiter with opaque, non-PII Redis keys."""

    def __init__(self, client: Redis, *, limit: int, window_seconds: int) -> None:
        self._client = client
        self._limit = limit
        self._window_ms = window_seconds * 1000

    async def acquire(self, *, owner_key: str, route_group: str) -> None:
        identity = hashlib.sha256(owner_key.encode()).hexdigest()
        group = hashlib.sha256(route_group.encode()).hexdigest()[:16]
        key = f"advisor:rate:v1:{group}:{identity}"
        try:
            pending = self._client.eval(_RATE_LIMIT_SCRIPT, 1, key, str(self._window_ms))
            raw = await cast(Awaitable[Any], pending)
        except RedisError as exc:
            raise RateLimitDependencyUnavailable from exc
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise RateLimitDependencyUnavailable
        count, ttl_ms = int(raw[0]), int(raw[1])
        if count > self._limit:
            raise RateLimitExceeded(max(1, (ttl_ms + 999) // 1000))


class RedisCachedMcpToolClient:
    """Caches only explicitly allowlisted, read-only MCP tool responses."""

    _READ_ONLY_TTLS = {
        "find_places": 300,
        "find_adoptions": 120,
        "get_weather_for_zip": 300,
        "lookup_pet_regulations": 3600,
        "search_current_guidance": 900,
    }

    def __init__(
        self,
        inner: McpToolClient,
        client: Redis,
        *,
        default_ttl_seconds: int,
    ) -> None:
        self._inner = inner
        self._redis = client
        self._default_ttl = default_ttl_seconds

    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: Mapping[str, object],
        timeout_seconds: float,
        authorization_audience: str | None = None,
        forwarded_user_assertion: str | None = None,
    ) -> Mapping[str, object]:
        if tool_name not in self._READ_ONLY_TTLS or forwarded_user_assertion is not None:
            return await self._inner.call_tool(
                server_url=server_url,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
                authorization_audience=authorization_audience,
                forwarded_user_assertion=forwarded_user_assertion,
            )
        key = self._key(server_url, tool_name, arguments)
        try:
            cached = await self._redis.get(key)
            if isinstance(cached, bytes):
                value = json.loads(cached)
                if isinstance(value, Mapping):
                    return value
        except (RedisError, UnicodeDecodeError, json.JSONDecodeError):
            pass

        response = await self._inner.call_tool(
            server_url=server_url,
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
            authorization_audience=authorization_audience,
        )
        ttl = self._READ_ONLY_TTLS.get(tool_name, self._default_ttl)
        try:
            encoded = json.dumps(response, sort_keys=True, separators=(",", ":"))
            await self._redis.set(key, encoded, ex=ttl)
        except (RedisError, TypeError, ValueError):
            pass
        return response

    @staticmethod
    def _key(server_url: str, tool_name: str, arguments: Mapping[str, object]) -> str:
        payload: dict[str, Any] = {
            "server": server_url,
            "tool": tool_name,
            "arguments": dict(arguments),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return f"advisor:mcp-cache:v1:{hashlib.sha256(encoded).hexdigest()}"
