"""Operational health probes kept outside the versioned product API contract."""

from typing import Literal, Protocol, cast

from fastapi import APIRouter, Request

from advisor_api.contracts.base import ContractModel
from advisor_api.http.errors import ServiceUnavailableError


class DatabaseProbe(Protocol):
    async def ping(self) -> None: ...


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"


router = APIRouter(include_in_schema=False)


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Report that the process can serve HTTP requests."""

    return HealthResponse()


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse:
    """Report readiness after startup validation and a current database ping."""

    runtime = cast(DatabaseProbe | None, request.app.state.database_runtime)
    if runtime is not None:
        try:
            await runtime.ping()
        except Exception as exc:
            raise ServiceUnavailableError() from exc
    return HealthResponse()
