"""Input / file validation helpers."""

from __future__ import annotations

import mimetypes
import os
import re
import unicodedata
from typing import Optional

from app.core.config import settings
from app.core.errors import InvalidFileError, ValidationFailedError

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ()\[\]]+")
_MAX_NAME_LEN = 255
DEFAULT_MIME = "application/octet-stream"


def sanitize_filename(name: Optional[str], fallback: str = "file.bin") -> str:
    """Strip paths, control characters and dangerous glyphs from a filename."""
    if not name:
        return fallback
    name = unicodedata.normalize("NFKC", name)
    name = name.replace("\x00", "")
    name = os.path.basename(name.replace("\\", "/")).strip()
    name = _SAFE_NAME_RE.sub("_", name).strip(" .")
    if not name:
        return fallback
    if len(name) > _MAX_NAME_LEN:
        root, ext = os.path.splitext(name)
        name = root[: _MAX_NAME_LEN - len(ext)] + ext
    return name


def guess_mime_type(filename: str, provided: Optional[str] = None) -> str:
    if provided and "/" in provided and provided != DEFAULT_MIME:
        return provided.split(";")[0].strip().lower()
    guessed, _ = mimetypes.guess_type(filename)
    return (guessed or provided or DEFAULT_MIME).lower()


def validate_upload(filename: str, mime_type: str, size: Optional[int]) -> None:
    """Raise if the file violates configured upload policy."""
    ext = os.path.splitext(filename)[1].lower()
    if ext and ext in {e.lower() for e in settings.BLOCKED_EXTENSIONS}:
        raise InvalidFileError(f"Files with the '{ext}' extension are not allowed.")
    if settings.ALLOWED_MIME_TYPES and mime_type not in settings.ALLOWED_MIME_TYPES:
        raise InvalidFileError(f"MIME type '{mime_type}' is not allowed.")
    if size is not None and size <= 0:
        raise InvalidFileError("The uploaded file is empty.")


def validate_metadata(metadata: Optional[dict]) -> dict:
    """User supplied metadata must be a small, flat, JSON-safe mapping."""
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValidationFailedError("metadata must be a JSON object.")
    if len(metadata) > 32:
        raise ValidationFailedError("metadata supports at most 32 keys.")
    clean: dict[str, object] = {}
    for key, value in metadata.items():
        key = str(key)[:64]
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value[:512] if isinstance(value, str) else value
        else:
            raise ValidationFailedError(
                f"metadata['{key}'] must be a string, number, boolean or null."
            )
    return clean


_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range_header(header: Optional[str], file_size: int) -> Optional[tuple[int, int]]:
    """Parse a single-range ``Range`` header into an inclusive ``(start, end)``.

    Returns ``None`` when no (or an unsupported multi-) range is requested, and
    raises :class:`ValueError` when the range is syntactically valid but cannot
    be satisfied.
    """
    if not header:
        return None
    match = _RANGE_RE.match(header.strip())
    if not match:
        return None
    raw_start, raw_end = match.group(1), match.group(2)
    if not raw_start and not raw_end:
        return None
    if file_size <= 0:
        raise ValueError("empty file")

    if not raw_start:  # suffix range: bytes=-500 -> last 500 bytes
        length = int(raw_end)
        if length <= 0:
            raise ValueError("invalid suffix range")
        start = max(file_size - length, 0)
        end = file_size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else file_size - 1
        end = min(end, file_size - 1)

    if start > end or start >= file_size:
        raise ValueError("unsatisfiable range")
    return start, end
