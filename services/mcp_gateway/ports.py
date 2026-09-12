"""Provider-neutral MCP client boundary."""

from collections.abc import Mapping
from typing import Protocol


class McpToolClient(Protocol):
    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: Mapping[str, object],
        timeout_seconds: float,
        authorization_audience: str | None = None,
        forwarded_user_assertion: str | None = None,
    ) -> Mapping[str, object]: ...


class IdTokenProvider(Protocol):
    """Issues a short-lived identity token for a private service audience."""

    async def token_for(self, audience: str) -> str: ...
