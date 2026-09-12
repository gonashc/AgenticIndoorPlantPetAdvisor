"""Official MCP Python SDK adapter hidden behind the local client port."""

from collections.abc import Mapping
from typing import Any, cast

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from services.mcp_gateway.ports import IdTokenProvider
from services.mcp_identity import FORWARDED_IAP_ASSERTION_HEADER


class McpSdkToolClient:
    def __init__(self, token_provider: IdTokenProvider | None = None) -> None:
        self._token_provider = token_provider

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
        if forwarded_user_assertion is not None and authorization_audience is None:
            raise ValueError("User assertions may be forwarded only to authenticated MCP services")
        if forwarded_user_assertion is not None and (
            not forwarded_user_assertion.strip()
            or "\r" in forwarded_user_assertion
            or "\n" in forwarded_user_assertion
        ):
            raise ValueError("The forwarded user assertion is invalid")
        if authorization_audience is None:
            async with Client(server_url, read_timeout_seconds=timeout_seconds) as client:
                result = await client.call_tool(
                    tool_name,
                    dict(arguments),
                    read_timeout_seconds=timeout_seconds,
                )
        else:
            if self._token_provider is None:
                raise ValueError("Private MCP service authentication is not configured")
            token = await self._token_provider.token_for(authorization_audience)
            timeout = httpx2.Timeout(timeout_seconds)
            headers = {"Authorization": f"Bearer {token}"}
            if forwarded_user_assertion is not None:
                # IAP strips client-supplied x-goog-* headers. Use a private,
                # non-reserved transport header and verify the assertion again
                # at the MCP service boundary.
                headers[FORWARDED_IAP_ASSERTION_HEADER] = forwarded_user_assertion
            async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client:
                transport = streamable_http_client(server_url, http_client=http_client)
                async with Client(transport, read_timeout_seconds=timeout_seconds) as client:
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
