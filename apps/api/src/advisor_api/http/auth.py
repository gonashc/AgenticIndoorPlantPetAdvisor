"""Authenticated request dependency shared by all versioned product endpoints."""

from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from advisor_api.container import get_container
from advisor_api.http.errors import RateLimitError, ServiceUnavailableError
from advisor_api.ports.auth import AuthenticatedUser, IdentityTokenVerifier
from advisor_api.ports.traffic import RateLimitDependencyUnavailable, RateLimitExceeded

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
    if token is not None:
        request.state.iap_assertion = token
    return principal


async def rate_limited_user(
    request: Request,
    principal: Annotated[AuthenticatedUser, Depends(authenticated_user)],
) -> AuthenticatedUser:
    route = request.scope.get("route")
    route_group = getattr(route, "name", request.url.path)
    try:
        await get_container(request).rate_limiter.acquire(
            owner_key=str(principal.owner_id),
            route_group=str(route_group),
        )
    except RateLimitExceeded as exc:
        raise RateLimitError(exc.retry_after_seconds) from exc
    except RateLimitDependencyUnavailable as exc:
        raise ServiceUnavailableError from exc
    return principal


def forwarded_iap_assertion(request: Request) -> str:
    """Return only the assertion already verified by the endpoint dependency."""

    token = getattr(request.state, "iap_assertion", None)
    if not isinstance(token, str) or not token:
        raise RuntimeError("A verified IAP assertion is required for the private MCP route")
    return token
