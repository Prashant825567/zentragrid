"""Auth package façade.

Keeps the ``app/auth/*`` layout from the spec while the real implementation
lives in the service layer, so there is exactly one owner-identity code path.
"""

from __future__ import annotations

from app.services.owner_service import OwnerService

__all__ = ["OwnerService"]
