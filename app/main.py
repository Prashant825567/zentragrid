"""ZentraGrid API application factory.

Run locally::

    uvicorn app.main:app --reload

On Render::

    uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.storage import get_storage

logger = logging.getLogger("zentragrid")

DESCRIPTION = """
ZentraGrid is a developer storage infrastructure API.

**Two authentication schemes**

| Audience | Header |
|---|---|
| Dashboard (owner) | `Authorization: Bearer <FIREBASE_ID_TOKEN>` |
| Developer API | `Authorization: Bearer ZTG_live_...` |

Persistence is provided by private Telegram channels behind repository
abstractions — there is no SQL/NoSQL application database.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "startup env=%s storage=%s firebase_configured=%s",
        settings.APP_ENV,
        settings.STORAGE_BACKEND,
        settings.firebase_configured,
    )

    if settings.is_production:
        if settings.AUTH_ALLOW_INSECURE_TOKENS:
            raise RuntimeError("AUTH_ALLOW_INSECURE_TOKENS must be false in production.")
        if settings.API_KEY_PEPPER == "change-me-in-production":
            raise RuntimeError("API_KEY_PEPPER must be set to a strong secret in production.")
        if "*" in settings.CORS_ORIGINS:
            raise RuntimeError("Wildcard CORS is not allowed in production.")

    # Initialise Firebase eagerly so misconfiguration fails fast at boot.
    if settings.firebase_configured:
        from app.auth.firebase import init_firebase

        init_firebase()

    storage = get_storage()
    try:
        await storage.warm()
    except Exception as exc:
        # A cold storage backend should not prevent the process from booting;
        # /health stays green and indexes load lazily on first use.
        logger.warning("storage_warm_failed error=%s", type(exc).__name__)

    yield

    try:
        await storage.usage.flush()
    except Exception:  # pragma: no cover
        logger.warning("usage_flush_on_shutdown_failed")

    if settings.STORAGE_BACKEND == "telegram":
        from app.telegram.client import close_client

        await close_client()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        description=DESCRIPTION,
        version="1.0.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=[
            "Content-Range",
            "Accept-Ranges",
            "Content-Length",
            "Content-Disposition",
            "X-Request-ID",
        ],
        max_age=600,
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.API_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "docs": None if settings.is_production else "/docs",
        }

    return app


app = create_app()
