"""API key generation and hashing.

Plaintext API keys are shown exactly once (at creation) and are never stored.
We persist an HMAC-SHA256 digest keyed with ``API_KEY_PEPPER`` so a leak of the
OWNERS channel alone cannot be replayed against the API.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.core.config import settings


def generate_api_key() -> str:
    """Return a fresh plaintext API key, e.g. ``ZTG_live_a1b2...``."""
    return f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(plaintext: str) -> str:
    """Deterministic, peppered digest used for lookups."""
    return hmac.new(
        settings.API_KEY_PEPPER.encode("utf-8"),
        plaintext.strip().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_api_key(plaintext: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(plaintext), expected_hash)


def mask_secret(value: str, visible: int = 4) -> str:
    """Safe representation for logs/UI: ``ZTG_live_…f4c1``."""
    if not value:
        return ""
    tail = value[-visible:] if len(value) > visible else ""
    return f"{settings.API_KEY_PREFIX}…{tail}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
