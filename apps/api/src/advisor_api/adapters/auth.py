"""Google IAP authentication adapter and local-only identity implementation."""

from asyncio import to_thread
from collections.abc import Mapping
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from advisor_api.http.errors import AuthenticationError
from advisor_api.ports.auth import AuthenticatedUser

IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"
IAP_ISSUER = "https://cloud.google.com/iap"
LOCAL_OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")


class LocalIdentityTokenVerifier:
    """Deterministic local/test identity; prohibited by production settings validation."""

    async def verify(self, token: str | None) -> AuthenticatedUser:
        del token
        return AuthenticatedUser(
            owner_id=LOCAL_OWNER_ID,
            subject="local-development-user",
            issuer="advisor-local",
        )


class GoogleIapTokenVerifier:
    """Verify signed IAP assertions and derive an internal, non-PII owner UUID."""

    def __init__(self, audience: str) -> None:
        self._audience = audience

    async def verify(self, token: str | None) -> AuthenticatedUser:
        if not token:
            raise AuthenticationError()
        try:
            claims = await to_thread(self._verify, token)
        except Exception as exc:
            raise AuthenticationError() from exc
        subject = claims.get("sub")
        issuer = claims.get("iss")
        if not isinstance(subject, str) or not subject or issuer != IAP_ISSUER:
            raise AuthenticationError()
        owner_id = uuid5(NAMESPACE_URL, f"{issuer}|{subject}")
        return AuthenticatedUser(owner_id=owner_id, subject=subject, issuer=issuer)

    def _verify(self, token: str) -> Mapping[str, Any]:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        claims = id_token.verify_token(
            token,
            Request(),
            audience=self._audience,
            certs_url=IAP_CERTS_URL,
        )
        return claims
