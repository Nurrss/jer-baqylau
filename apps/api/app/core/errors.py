"""Domain errors and their mapping to the unified HTTP error format.

Every error response has the shape ``{"error": {"code", "message", "details"}}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


class DomainError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class InvalidTransitionError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "INVALID_TRANSITION"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class ValidationFailedError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "VALIDATION_ERROR"


class AuthError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class RateLimitedError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            error_body("VALIDATION_ERROR", "Request validation failed", {"errors": errors}),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 405: "METHOD_NOT_ALLOWED"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(
            error_body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path, method=request.method)
        return JSONResponse(
            error_body("INTERNAL_ERROR", "Internal server error"),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
