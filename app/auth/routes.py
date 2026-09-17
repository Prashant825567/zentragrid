"""Auth package façade — re-exports the mounted auth router."""

from __future__ import annotations

from app.api.routes.auth import router

__all__ = ["router"]
