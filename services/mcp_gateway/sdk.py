"""Official MCP Python SDK adapter hidden behind the local client port."""

from collections.abc import Mapping
from typing import Any, cast

from mcp import Client


class McpSdkToolClient:
    async def call_tool(
        self,
        *,
        server_url: str,
        tool_name: str,
        arguments: Mapping[str, object],
        timeout_seconds: float,
    ) -> Mapping[str, object]:
        async with Client(server_url, read_timeout_seconds=timeout_seconds) as client:
            result = await client.call_tool(
                tool_name,
                dict(arguments),
                read_timeout_seconds=timeout_seconds,
            )
        if result.is_error:
            raise RuntimeError(f"MCP tool {tool_name!r} reported an error")
        if result.structured_content is None:
            raise ValueError(f"MCP tool {tool_name!r} returned no structured content")
        return cast(Mapping[str, Any], result.structured_content)
