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
    from app.auth.firebase import auth_mode
    from app.telegram.client import healthcheck

    storage_status = await healthcheck()
    mode = auth_mode()
    ready = bool(storage_status.get("connected")) and mode != "unconfigured"
    return {
        "status": "ready" if ready else "degraded",
        "storage": storage_status,
        "auth_mode": mode,
        "auth_ready": mode in {"admin", "jwks", "insecure"},
        "firebase_project_id": settings.FIREBASE_PROJECT_ID or None,
        "service_account_key": settings.firebase_configured,
    }
