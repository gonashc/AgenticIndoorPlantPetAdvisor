"""Short-lived identity tokens for private MCP services."""

from asyncio import to_thread
from typing import cast


class GoogleCloudRunIdTokenProvider:
    """Uses Application Default Credentials to call a private Cloud Run service."""

    async def token_for(self, audience: str) -> str:
        return await to_thread(self._fetch, audience)

    @staticmethod
    def _fetch(audience: str) -> str:
        from google.auth.transport.requests import Request
        from google.oauth2.id_token import fetch_id_token

        return cast(str, fetch_id_token(Request(), audience))  # type: ignore[no-untyped-call]
