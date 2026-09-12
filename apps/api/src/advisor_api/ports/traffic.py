"""Provider-neutral request-throttling boundary."""

from typing import Protocol


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Request rate limit exceeded")
        self.retry_after_seconds = max(1, retry_after_seconds)


class RateLimitDependencyUnavailable(Exception):
    pass


class RequestRateLimiter(Protocol):
    async def acquire(self, *, owner_key: str, route_group: str) -> None: ...


class NoopRequestRateLimiter:
    async def acquire(self, *, owner_key: str, route_group: str) -> None:
        del owner_key, route_group
