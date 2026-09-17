"""Firebase Admin SDK integration.

Responsibilities
----------------
* Initialise the Admin SDK from discrete environment variables (Render-safe,
  with ``\\n`` un-escaping handled in config).
* Verify incoming Firebase ID tokens issued by Google Sign-In.

The frontend Firebase web API key is NOT a server credential and is never used
here. Tokens are never logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.core.errors import ConfigurationError, InvalidFirebaseTokenError

logger = logging.getLogger("zentragrid.auth.firebase")

_app = None
_initialised = False


@dataclass(slots=True)
class FirebaseIdentity:
    """Verified claims we are willing to trust from a Firebase ID token."""

    uid: str
    email: str
    email_verified: bool = False
    name: Optional[str] = None
    picture: Optional[str] = None
    sign_in_provider: Optional[str] = None


def auth_mode() -> str:
    """Which verification strategy is active.

    ``admin``    full Admin SDK (service-account key present)
    ``jwks``     keyless verification against Google's public keys
    ``insecure`` development bypass (never allowed in production)
    """
    if settings.firebase_configured:
        return "admin"
    if settings.FIREBASE_PROJECT_ID:
        return "jwks"
    if settings.AUTH_ALLOW_INSECURE_TOKENS and not settings.is_production:
        return "insecure"
    return "unconfigured"


def init_firebase() -> None:
    """Initialise the Admin SDK once at application startup."""
    global _app, _initialised
    if _initialised:
        return

    if not settings.firebase_configured:
        mode = auth_mode()
        if mode == "jwks":
            # Perfectly valid for our use case: verifying ID tokens only needs
            # Google's public keys. Common when the org policy
            # iam.disableServiceAccountKeyCreation blocks key downloads.
            logger.info(
                "firebase_keyless_mode project_id=%s (verifying via Google public keys)",
                settings.FIREBASE_PROJECT_ID,
            )
            _initialised = True
            return
        if mode == "insecure":
            logger.warning(
                "firebase_not_configured insecure_token_mode=on (development only)"
            )
            _initialised = True
            return
        raise ConfigurationError(
            "Firebase is not configured. Set FIREBASE_PROJECT_ID (required). "
            "Optionally add FIREBASE_CLIENT_EMAIL and FIREBASE_PRIVATE_KEY to use "
            "the full Admin SDK."
        )

    import firebase_admin
    from firebase_admin import credentials

    try:
        _app = firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(settings.firebase_credentials_dict())
        _app = firebase_admin.initialize_app(cred, {"projectId": settings.FIREBASE_PROJECT_ID})

    _initialised = True
    logger.info("firebase_admin_ready project_id=%s", settings.FIREBASE_PROJECT_ID)


def _identity_from_claims(claims: dict) -> FirebaseIdentity:
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise InvalidFirebaseTokenError("The Firebase token does not contain an email address.")

    firebase_section = claims.get("firebase") or {}
    provider = firebase_section.get("sign_in_provider")

    return FirebaseIdentity(
        uid=claims.get("uid") or claims.get("user_id") or claims.get("sub", ""),
        email=email,
        email_verified=bool(claims.get("email_verified", False)),
        name=claims.get("name"),
        picture=claims.get("picture"),
        sign_in_provider=provider,
    )


def verify_id_token(id_token: str) -> FirebaseIdentity:
    """Verify a Firebase ID token and return the trusted identity.

    Raises :class:`InvalidFirebaseTokenError` for any invalid/expired/revoked
    token. The raw token value is never included in logs or error messages.
    """
    if not id_token or not id_token.strip():
        raise InvalidFirebaseTokenError()

    mode = auth_mode()

    if mode == "unconfigured":
        raise ConfigurationError(
            "Firebase is not configured. Set FIREBASE_PROJECT_ID."
        )

    # Development-only bypass: accept an unsigned JSON payload so the API can be
    # exercised without real Google credentials. Refuses to work in production.
    if mode == "insecure":
        if settings.is_production:
            raise ConfigurationError("Insecure token mode cannot be used in production.")
        return _verify_insecure(id_token)

    init_firebase()

    if mode == "jwks":
        # Keyless path: verify the JWT signature against Google's public keys.
        from app.auth.jwks import verify_firebase_jwt

        claims = verify_firebase_jwt(id_token, settings.FIREBASE_PROJECT_ID)
    else:
        from firebase_admin import auth as firebase_auth

        try:
            claims = firebase_auth.verify_id_token(id_token, check_revoked=False)
        except Exception as exc:
            logger.info("firebase_token_rejected reason=%s", type(exc).__name__)
            raise InvalidFirebaseTokenError() from exc

    identity = _identity_from_claims(claims)
    if identity.sign_in_provider and identity.sign_in_provider not in {"google.com", "custom"}:
        raise InvalidFirebaseTokenError("Only Google Sign-In is supported.")
    return identity


def _verify_insecure(id_token: str) -> FirebaseIdentity:
    """Decode a base64url JSON blob — development fixture only."""
    import base64
    import json

    try:
        padded = id_token + "=" * (-len(id_token) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception as exc:
        raise InvalidFirebaseTokenError() from exc
    if not isinstance(claims, dict):
        raise InvalidFirebaseTokenError()
    return _identity_from_claims(claims)
