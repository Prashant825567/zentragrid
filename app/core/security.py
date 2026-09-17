"""Authentication & authorization dependencies.

Two independent auth schemes:

* **Dashboard** – ``Authorization: Bearer <FIREBASE_ID_TOKEN>`` verified with
  the Firebase Admin SDK, resolved to an owner record.
* **Developer API** – ``Authorization: Bearer ZTG_live_…`` hashed and looked up
  in the API-key index, resolved to an (owner, project) pair.

Ownership is ALWAYS derived from the authenticated principal. ``owner_id`` /
``project_id`` supplied in a request body or path is never trusted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request

from app.auth.firebase import FirebaseIdentity, verify_id_token
from app.core.config import settings
from app.core.errors import (
    ForbiddenError,
    InvalidApiKeyError,
    InvalidFirebaseTokenError,
    ProfileIncompleteError,
    ProjectNotFoundError,
    RevokedApiKeyError,
)
from app.core.ratelimit import enforce
from app.core.storage import Storage, get_storage
from app.models.api_key import ApiKey
from app.models.owner import Owner
from app.models.project import Project

logger = logging.getLogger("zentragrid.security")


@dataclass(slots=True)
class ApiPrincipal:
    """Resolved developer-API caller."""

    owner_id: str
    project_id: str
    key_id: str
    project: Project
    api_key: ApiKey


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise InvalidFirebaseTokenError("Missing or malformed Authorization header.")
    return token.strip()


def storage_dep() -> Storage:
    return get_storage()


# ------------------------------------------------------------------ dashboard
async def get_firebase_identity(request: Request) -> FirebaseIdentity:
    token = _bearer_token(request)
    if token.startswith(settings.API_KEY_PREFIX):
        raise InvalidFirebaseTokenError(
            "This endpoint requires a Firebase ID token, not a ZentraGrid API key."
        )
    identity = verify_id_token(token)
    await enforce("uid", identity.uid, "dashboard")
    request.state.owner_email_hint = identity.uid  # uid only, never the token
    return identity


async def get_current_owner(
    identity: FirebaseIdentity = Depends(get_firebase_identity),
    storage: Storage = Depends(storage_dep),
) -> Owner:
    """Resolve the authenticated Firebase user to an existing owner record."""
    owner = await storage.owners.get_by_email(identity.email)
    if owner is None:
        owner = await storage.owners.get_by_firebase_uid(identity.uid)
    if owner is None:
        raise InvalidFirebaseTokenError(
            "No ZentraGrid owner exists for this Google account. Call POST /v1/auth/google first."
        )
    if owner.disabled:
        raise ForbiddenError("This account has been disabled.")
    return owner


async def get_active_owner(owner: Owner = Depends(get_current_owner)) -> Owner:
    """Like :func:`get_current_owner` but requires a completed profile."""
    if not owner.profile_completed:
        raise ProfileIncompleteError()
    return owner


async def get_owner_project(
    project_id: str,
    owner: Owner = Depends(get_active_owner),
    storage: Storage = Depends(storage_dep),
) -> Project:
    """Path-scoped project fetch that enforces owner isolation."""
    project = await storage.projects.get_for_owner(project_id, owner.owner_id)
    if project is None:
        # 404 rather than 403 so project ids of other owners are not enumerable.
        raise ProjectNotFoundError()
    return project


# ----------------------------------------------------------------- developer
async def get_api_principal(
    request: Request,
    storage: Storage = Depends(storage_dep),
) -> ApiPrincipal:
    """Authenticate a developer request using a ZentraGrid API key."""
    token = _bearer_token(request)
    if not token.startswith(settings.API_KEY_PREFIX):
        raise InvalidApiKeyError()

    key = await storage.api_keys.get_by_plaintext(token)
    if key is None:
        # Never log the key itself — only that a lookup failed.
        logger.info("api_key_lookup_failed path=%s", request.url.path)
        raise InvalidApiKeyError()
    if key.revoked:
        raise RevokedApiKeyError()

    project = await storage.projects.get(key.project_id)
    if project is None or project.deleted:
        raise InvalidApiKeyError("The project for this API key no longer exists.")

    owner = await storage.owners.get(key.owner_id)
    if owner is None or owner.disabled:
        raise InvalidApiKeyError("The owner for this API key is not active.")

    request.state.project_id = project.project_id
    request.state.key_id = key.key_id

    return ApiPrincipal(
        owner_id=key.owner_id,
        project_id=key.project_id,
        key_id=key.key_id,
        project=project,
        api_key=key,
    )


def rate_limited(operation: str):
    """Dependency factory applying a per-API-key limit for an operation class."""

    async def _dependency(principal: ApiPrincipal = Depends(get_api_principal)) -> ApiPrincipal:
        await enforce("key", principal.key_id, operation)
        return principal

    return _dependency


def security_headers(response_headers: dict, is_https: bool = True) -> dict:
    """Baseline hardening headers applied to every response."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Resource-Policy": "same-site",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Cache-Control": "no-store",
    }
    if is_https and settings.is_production:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response_headers.update(headers)
    return response_headers


def optional_bearer(request: Request) -> Optional[str]:
    try:
        return _bearer_token(request)
    except InvalidFirebaseTokenError:
        return None
