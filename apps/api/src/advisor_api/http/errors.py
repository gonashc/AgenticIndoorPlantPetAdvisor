"""Versioned error hierarchy and FastAPI exception mapping."""

from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from advisor_api.contracts.base import Category
from advisor_api.contracts.errors import ErrorBody, ErrorDetail, ErrorEnvelope


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[ErrorDetail] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers or {}


class AuthenticationError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            HTTPStatus.UNAUTHORIZED,
            "AUTHENTICATION_REQUIRED",
            "A valid authenticated session is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class CategoryUnavailableError(ApiError):
    def __init__(self, category: Category) -> None:
        super().__init__(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "CATEGORY_NOT_AVAILABLE",
            f"{category.value.title()} recommendations are not enabled in this release.",
        )


class NotFoundError(ApiError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            HTTPStatus.NOT_FOUND,
            "RESOURCE_NOT_FOUND",
            f"The requested {resource} was not found.",
            [ErrorDetail(code="NOT_FOUND", message="No matching resource.", field=resource)],
        )


class ConflictError(ApiError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(HTTPStatus.CONFLICT, code, message)


class ServiceUnavailableError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "SERVICE_UNAVAILABLE",
            "The service is not ready to accept traffic.",
        )


class NoEligibleCandidatesError(ApiError):
    def __init__(self, category: Category) -> None:
        super().__init__(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "NO_ELIGIBLE_CANDIDATES",
            "No candidates satisfy the submitted hard constraints.",
            [
                ErrorDetail(
                    field="category",
                    code="NO_SAFE_MATCH",
                    message=f"No eligible {category.value} candidates were found.",
                )
            ],
        )


def _request_id(request: Request) -> UUID:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, UUID) else uuid4()


def _response(
    error: ErrorEnvelope, status_code: int, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(mode="json"),
        headers={"X-Error-Contract-Version": "v1", **(headers or {})},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
                details=exc.details,
            )
        )
        return _response(envelope, exc.status_code, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(part) for part in error["loc"]),
                code=str(error["type"]),
                message=str(error["msg"]),
            )
            for error in exc.errors()
        ]
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code="REQUEST_VALIDATION_FAILED",
                message="The request did not satisfy the v1 contract.",
                request_id=_request_id(request),
                details=details,
            )
        )
        return _response(envelope, HTTPStatus.UNPROCESSABLE_ENTITY)

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code="HTTP_ERROR",
                message=str(exc.detail),
                request_id=_request_id(request),
            )
        )
        return _response(envelope, exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        del exc
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code="INTERNAL_ERROR",
                message="The request could not be completed.",
                request_id=_request_id(request),
            )
        )
        return _response(envelope, HTTPStatus.INTERNAL_SERVER_ERROR)


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope, "description": "Authentication required"},
    404: {"model": ErrorEnvelope, "description": "Resource not found"},
    409: {"model": ErrorEnvelope, "description": "State conflict"},
    422: {"model": ErrorEnvelope, "description": "Validation or eligibility failure"},
    500: {"model": ErrorEnvelope, "description": "Unexpected server failure"},
}
