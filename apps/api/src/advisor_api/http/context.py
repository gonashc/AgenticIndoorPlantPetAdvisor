"""Correlation and version response headers."""

from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Request-ID")
        try:
            request_id = UUID(supplied) if supplied else uuid4()
        except ValueError:
            request_id = uuid4()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request_id)
        response.headers["X-API-Version"] = "v1"
        return response


def request_id(request: Request) -> UUID:
    value = request.state.request_id
    if not isinstance(value, UUID):
        raise RuntimeError("Request context middleware is not installed")
    return value
