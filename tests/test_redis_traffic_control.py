"""Redis caching and request-limit behavior without a live server."""

import os
from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

import pytest
from advisor_api.ports.traffic import RateLimitExceeded

from services.traffic_control import (
    RedisCachedMcpToolClient,
    RedisRequestRateLimiter,
    create_redis_runtime,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.count = 0

    async def eval(self, script: str, keys: int, key: str, window: str) -> list[int]:
        del script, keys, key, window
        self.count += 1
        return [self.count, 60_000]

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        assert ex > 0
        self.values[key] = value.encode()
        return True


class StubMcpClient:
    def __init__(self) -> None:
        self.calls = 0

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
        del server_url, tool_name, arguments, timeout_seconds
        del authorization_audience, forwarded_user_assertion
        self.calls += 1
        return {"sources": []}


@pytest.mark.asyncio
async def test_redis_rate_limiter_uses_atomic_counter() -> None:
    limiter = RedisRequestRateLimiter(
        cast(Any, FakeRedis()),
        limit=1,
        window_seconds=60,
    )

    await limiter.acquire(owner_key="owner", route_group="recommendations")
    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter.acquire(owner_key="owner", route_group="recommendations")

    assert exc_info.value.retry_after_seconds == 60


@pytest.mark.asyncio
async def test_read_only_mcp_responses_are_cached() -> None:
    redis = FakeRedis()
    inner = StubMcpClient()
    client = RedisCachedMcpToolClient(
        inner,
        cast(Any, redis),
        default_ttl_seconds=300,
    )
    arguments = {"category": "PLANT", "zip_code": "10001"}

    first = await client.call_tool(
        server_url="https://places.example/mcp",
        tool_name="find_places",
        arguments=arguments,
        timeout_seconds=4,
    )
    second = await client.call_tool(
        server_url="https://places.example/mcp",
        tool_name="find_places",
        arguments=arguments,
        timeout_seconds=4,
    )

    assert first == second == {"sources": []}
    assert inner.calls == 1


@pytest.mark.asyncio
async def test_real_redis_rate_limit_integration() -> None:
    redis_url = os.getenv("TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("TEST_REDIS_URL is not configured")
    runtime = create_redis_runtime(redis_url, socket_timeout_seconds=1)
    limiter = RedisRequestRateLimiter(runtime.client, limit=1, window_seconds=10)
    owner = str(uuid4())
    try:
        await runtime.verify()
        await limiter.acquire(owner_key=owner, route_group="integration")
        with pytest.raises(RateLimitExceeded):
            await limiter.acquire(owner_key=owner, route_group="integration")
    finally:
        await runtime.close()
