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
    ) -> Mapping[str, object]: ...
