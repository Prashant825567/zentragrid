"""Permanent, tamper-proof public download links.

A public link is ``/dl/{file_id}?sig={signature}`` where ``signature`` is a
truncated HMAC-SHA256 over the file id. No auth header is needed to use one,
so it can be pasted straight into a browser — the signature *is* the
capability.

Key material
------------
``PUBLIC_LINK_SECRET`` when set, otherwise derived from ``TG_SESSION`` (which
is already a deployment secret). Rotating either invalidates every previously
issued link — signatures can simply be reissued, they cost nothing.

Threat model
------------
The signature prevents forging links for *other* files. Anyone holding a link
can download that file forever (or until the secret rotates) — that is the
point of a public link. Signature verification runs before any storage lookup
so file ids cannot be enumerated through this route.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings

_CONTEXT = "zentragrid-public-link-v1:"
_SIG_CHARS = 32  # 128 bits of HMAC output — plenty for an unforgeable URL


def _signing_key() -> bytes:
    material = settings.PUBLIC_LINK_SECRET or settings.TG_SESSION or "zentragrid-dev-insecure"
    return hashlib.sha256(f"{_CONTEXT}{material}".encode()).digest()


def sign_file_id(file_id: str) -> str:
    """Return the permanent signature for ``file_id``."""
    return hmac.new(_signing_key(), file_id.encode(), hashlib.sha256).hexdigest()[:_SIG_CHARS]


def verify_signature(file_id: str, signature: str | None) -> bool:
    """Constant-time check; empty/None/tampered signatures all fail."""
    if not signature:
        return False
    return hmac.compare_digest(sign_file_id(file_id), signature.strip().lower())
