"""Authenticated request dependency shared by all versioned product endpoints."""

from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from advisor_api.ports.auth import AuthenticatedUser, IdentityTokenVerifier

iap_assertion = APIKeyHeader(
    name="X-Goog-IAP-JWT-Assertion",
    scheme_name="GoogleIapAssertion",
    description="Signed assertion injected by Google Cloud Identity-Aware Proxy.",
    auto_error=False,
)


async def authenticated_user(
    request: Request,
    token: Annotated[str | None, Depends(iap_assertion)],
) -> AuthenticatedUser:
    verifier = cast(IdentityTokenVerifier, request.app.state.identity_token_verifier)
    principal = await verifier.verify(token)
    request.state.authenticated_user = principal
    return principal
