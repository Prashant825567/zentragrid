"""Health & readiness."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Never touches Telegram so Render's health check stays fast and cheap."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "storage_backend": settings.STORAGE_BACKEND,
    }


@router.get("/health/ready", summary="Readiness probe (checks dependencies)")
async def readiness() -> dict:
    from app.telegram.client import healthcheck

    storage_status = await healthcheck()
    ready = bool(storage_status.get("connected")) and (
        settings.firebase_configured or settings.AUTH_ALLOW_INSECURE_TOKENS
    )
    return {
        "status": "ready" if ready else "degraded",
        "storage": storage_status,
        "firebase_configured": settings.firebase_configured,
    }
