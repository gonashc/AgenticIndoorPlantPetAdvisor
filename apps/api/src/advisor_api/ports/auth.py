"""Provider-neutral authenticated principal and token-verification port."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal identity propagated to ownership checks; excludes profile PII."""

    owner_id: UUID
    subject: str
    issuer: str


class IdentityTokenVerifier(Protocol):
    async def verify(self, token: str | None) -> AuthenticatedUser: ...
