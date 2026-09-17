"""Keyless Firebase ID-token verification.

Firebase ID tokens are ordinary RS256 JWTs signed by Google. Verifying one only
needs Google's **public** signing certificates — no service-account private key
is involved. The Admin SDK does exactly this internally; it just also needs a
credential for the *other* things it can do (minting custom tokens, managing
users, etc.), none of which ZentraGrid uses.

This module is the fallback used when ``FIREBASE_CLIENT_EMAIL`` /
``FIREBASE_PRIVATE_KEY`` are unavailable — typically because the Google Cloud
org policy ``iam.disableServiceAccountKeyCreation`` blocks key downloads.

Security is equivalent for our purposes: we check the signature against
Google's published keys plus every claim Firebase requires (``iss``, ``aud``,
``exp``, ``iat``, ``sub``). The one thing it cannot do is detect a token
revoked mid-lifetime, which ``check_revoked=True`` would catch — and we don't
use that anyway (tokens are short-lived, one hour).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from app.core.errors import ConfigurationError, InvalidFirebaseTokenError

logger = logging.getLogger("zentragrid.auth.jwks")

JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
ISSUER_PREFIX = "https://securetoken.google.com/"

# Google rotates these roughly daily and sets a long max-age; an hour is a safe
# refresh interval that also bounds how long a rotated-out key stays cached.
_CACHE_TTL = 3600

_lock = threading.Lock()
_cached_keys: dict[str, Any] = {}
_cached_at: float = 0.0


def _fetch_jwks() -> dict[str, Any]:
    """Download Google's current public signing keys, keyed by ``kid``."""
    import httpx
    from jwt.algorithms import RSAAlgorithm

    try:
        response = httpx.get(JWKS_URL, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.error("jwks_fetch_failed error=%s", type(exc).__name__)
        raise InvalidFirebaseTokenError(
            "Could not reach Google's token verification service."
        ) from exc

    keys: dict[str, Any] = {}
    for key in payload.get("keys", []):
        kid = key.get("kid")
        if kid:
            try:
                keys[kid] = RSAAlgorithm.from_jwk(key)
            except Exception:  # pragma: no cover
                logger.warning("jwks_key_parse_failed kid=%s", kid)
    if not keys:
        raise InvalidFirebaseTokenError("No usable Google signing keys found.")
    return keys


def _get_key(kid: str):
    """Return the public key for ``kid``, refreshing the cache if needed."""
    global _cached_keys, _cached_at

    with _lock:
        fresh = _cached_keys and (time.time() - _cached_at) < _CACHE_TTL
        if fresh and kid in _cached_keys:
            return _cached_keys[kid]

    # Cache miss or stale: refetch outside the lock, then swap in.
    keys = _fetch_jwks()
    with _lock:
        _cached_keys = keys
        _cached_at = time.time()

    key = keys.get(kid)
    if key is None:
        # Unknown kid after a fresh fetch means the token wasn't signed by Google.
        raise InvalidFirebaseTokenError()
    return key


def verify_firebase_jwt(id_token: str, project_id: str) -> dict[str, Any]:
    """Verify a Firebase ID token and return its claims.

    Raises :class:`InvalidFirebaseTokenError` for anything invalid. The token
    itself never appears in logs or error messages.
    """
    if not project_id:
        raise ConfigurationError("FIREBASE_PROJECT_ID is required to verify ID tokens.")

    import jwt

    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as exc:
        raise InvalidFirebaseTokenError() from exc

    kid = header.get("kid")
    if not kid or header.get("alg") != "RS256":
        raise InvalidFirebaseTokenError()

    key = _get_key(kid)

    try:
        claims = jwt.decode(
            id_token,
            key=key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"{ISSUER_PREFIX}{project_id}",
            options={
                "require": ["exp", "iat", "aud", "iss", "sub"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_signature": True,
            },
            leeway=30,  # tolerate small clock skew between Render and Google
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidFirebaseTokenError("The Firebase ID token has expired.") from exc
    except jwt.InvalidAudienceError as exc:
        raise InvalidFirebaseTokenError(
            "The Firebase ID token was issued for a different project."
        ) from exc
    except Exception as exc:
        logger.info("jwt_rejected reason=%s", type(exc).__name__)
        raise InvalidFirebaseTokenError() from exc

    # Firebase guarantees a non-empty sub, which is the user's UID.
    if not claims.get("sub"):
        raise InvalidFirebaseTokenError()
    claims.setdefault("uid", claims["sub"])

    return claims


def healthcheck() -> dict[str, Any]:
    """Report whether Google's signing keys are reachable."""
    try:
        keys = _fetch_jwks()
        return {"mode": "jwks", "reachable": True, "keys": len(keys)}
    except Exception as exc:
        return {"mode": "jwks", "reachable": False, "error": type(exc).__name__}
