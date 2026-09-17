"""Identifier helpers.

All public identifiers are opaque, prefixed and URL safe. They carry no
information about the underlying Telegram storage.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone

_ALPHABET = string.ascii_lowercase + string.digits


def _random(length: int = 16) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_id(prefix: str, length: int = 16) -> str:
    return f"{prefix}_{_random(length)}"


def new_owner_id() -> str:
    return new_id("owner")


def new_project_id() -> str:
    return new_id("project")


def new_key_id() -> str:
    return new_id("key")


def new_file_id() -> str:
    return new_id("file", 20)


def new_request_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """RFC3339 / ISO-8601 timestamp with a trailing Z."""
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")
