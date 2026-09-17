"""Unified error model.

Every error returned by the API has the shape::

    {"error": {"code": "INVALID_API_KEY", "message": "..."}}
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("zentragrid.errors")


class ZentraGridError(Exception):
    """Base class for all domain errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)

    def to_payload(self) -> dict:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


# --------------------------------------------------------------------- 400
class BadRequestError(ZentraGridError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    message = "The request was invalid."


class ValidationFailedError(BadRequestError):
    code = "VALIDATION_ERROR"
    message = "Request validation failed."


class InvalidFileError(BadRequestError):
    code = "INVALID_FILE"
    message = "The uploaded file is invalid."


# --------------------------------------------------------------------- 401
class UnauthorizedError(ZentraGridError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "Authentication is required."


class InvalidApiKeyError(UnauthorizedError):
    code = "INVALID_API_KEY"
    message = "The provided API key is invalid."


class RevokedApiKeyError(UnauthorizedError):
    code = "REVOKED_API_KEY"
    message = "The provided API key has been revoked."


class InvalidFirebaseTokenError(UnauthorizedError):
    code = "INVALID_ID_TOKEN"
    message = "The Firebase ID token is missing, expired or invalid."


# --------------------------------------------------------------------- 403
class ForbiddenError(ZentraGridError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "You do not have access to this resource."


class ProfileIncompleteError(ZentraGridError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "PROFILE_INCOMPLETE"
    message = "Owner profile must be completed before using the dashboard."


# --------------------------------------------------------------------- 404
class NotFoundError(ZentraGridError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "Resource not found."


class FileNotFoundError_(NotFoundError):  # noqa: N801 - avoid shadowing builtin
    code = "FILE_NOT_FOUND"
    message = "The requested file does not exist."


class ProjectNotFoundError(NotFoundError):
    code = "PROJECT_NOT_FOUND"
    message = "The requested project does not exist."


class OwnerNotFoundError(NotFoundError):
    code = "OWNER_NOT_FOUND"
    message = "The requested owner does not exist."


class ApiKeyNotFoundError(NotFoundError):
    code = "API_KEY_NOT_FOUND"
    message = "The requested API key does not exist."


# --------------------------------------------------------------------- 409
class ConflictError(ZentraGridError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "The resource already exists or is in a conflicting state."


class DuplicateOwnerError(ConflictError):
    code = "OWNER_ALREADY_EXISTS"
    message = "An owner with this email already exists."


# --------------------------------------------------------------------- 413
class PayloadTooLargeError(ZentraGridError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "PAYLOAD_TOO_LARGE"
    message = "The uploaded file exceeds the maximum allowed size."


class QuotaExceededError(ZentraGridError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "QUOTA_EXCEEDED"
    message = "Storage quota exceeded for this project."


# --------------------------------------------------------------------- 416
class RangeNotSatisfiableError(ZentraGridError):
    status_code = status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE
    code = "RANGE_NOT_SATISFIABLE"
    message = "The requested byte range cannot be satisfied."


# --------------------------------------------------------------------- 429
class RateLimitedError(ZentraGridError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "Too many requests. Please slow down."


# --------------------------------------------------------------------- 5xx
class StorageBackendError(ZentraGridError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "STORAGE_UNAVAILABLE"
    message = "The storage backend is temporarily unavailable."


class ConfigurationError(ZentraGridError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "CONFIGURATION_ERROR"
    message = "The server is misconfigured."


# ------------------------------------------------------------------ wiring
def _response(exc: ZentraGridError, request: Request) -> JSONResponse:
    headers = {}
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["X-Request-ID"] = request_id
    if isinstance(exc, RateLimitedError) and exc.details and "retry_after" in exc.details:
        headers["Retry-After"] = str(exc.details["retry_after"])
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload(), headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ZentraGridError)
    async def _zentragrid_error(request: Request, exc: ZentraGridError):
        if exc.status_code >= 500:
            logger.error("domain_error code=%s message=%s", exc.code, exc.message)
        return _response(exc, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", [])), "issue": err.get("msg")}
            for err in exc.errors()
        ]
        return _response(
            ValidationFailedError(details={"errors": details[:20]}),
            request,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        mapping = {
            400: ("BAD_REQUEST", "The request was invalid."),
            401: ("UNAUTHORIZED", "Authentication is required."),
            403: ("FORBIDDEN", "You do not have access to this resource."),
            404: ("NOT_FOUND", "Resource not found."),
            405: ("METHOD_NOT_ALLOWED", "Method not allowed for this route."),
            409: ("CONFLICT", "Conflicting state."),
            413: ("PAYLOAD_TOO_LARGE", "Payload too large."),
            429: ("RATE_LIMITED", "Too many requests."),
        }
        code, default_message = mapping.get(exc.status_code, ("HTTP_ERROR", "Request failed."))
        message = exc.detail if isinstance(exc.detail, str) else default_message
        return _response(
            ZentraGridError(message, code=code, status_code=exc.status_code), request
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # pragma: no cover
        logger.exception("unhandled_exception path=%s", request.url.path)
        return _response(ZentraGridError(), request)
