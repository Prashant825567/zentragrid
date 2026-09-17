"""Structured request logging.

Logged: request id, method, route, status, duration, project/file id.
NEVER logged: Firebase ID tokens, API keys, the Telegram session string, the
Firebase private key, or any Authorization header value.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.security import security_headers
from app.utils.ids import new_request_id

REDACTED_HEADERS = {"authorization", "cookie", "x-api-key", "proxy-authorization"}
SENSITIVE_ENV_KEYS = {
    "TG_SESSION",
    "TG_API_HASH",
    "FIREBASE_PRIVATE_KEY",
    "API_KEY_PEPPER",
}

logger = logging.getLogger("zentragrid.access")


class SecretRedactingFilter(logging.Filter):
    """Last line of defence: scrub known secret values out of log records."""

    def __init__(self) -> None:
        super().__init__()
        self._secrets = [
            value
            for value in (
                settings.TG_SESSION,
                settings.TG_API_HASH,
                settings.FIREBASE_PRIVATE_KEY,
                settings.API_KEY_PEPPER,
            )
            if value and len(str(value)) > 8
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        redacted = message
        for secret in self._secrets:
            if str(secret) in redacted:
                redacted = redacted.replace(str(secret), "***REDACTED***")
        if settings.API_KEY_PREFIX in redacted:
            import re

            redacted = re.sub(rf"{settings.API_KEY_PREFIX}[A-Za-z0-9_\-]+", "ZTG_live_***", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(SecretRedactingFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())

    # Telethon is extremely chatty at INFO and can echo session internals.
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request and applies security headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or new_request_id()
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed id=%s method=%s path=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        security_headers(response.headers, is_https=request.url.scheme == "https")

        logger.info(
            "request id=%s method=%s path=%s status=%s duration_ms=%.1f project_id=%s file_id=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            getattr(request.state, "project_id", "-"),
            getattr(request.state, "file_id", "-"),
        )
        return response
