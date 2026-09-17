"""Storage-layer contracts + JSON record encoding.

These abstract classes are the ONLY thing the repository layer talks to.
Swapping Telegram for S3/Postgres later means writing new implementations of
:class:`RecordChannel` and :class:`MediaChannel` — no repository or service
code has to change.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

RECORD_MARKER = "#zg_record"


@dataclass(slots=True)
class StoredRecord:
    """A structured record plus its storage-level pointer (message id)."""

    message_id: int
    data: dict[str, Any]


@dataclass(slots=True)
class StoredMedia:
    """Pointer to an uploaded blob in the media channel."""

    message_id: int
    size: int
    mime_type: Optional[str] = None
    filename: Optional[str] = None


def encode_record(data: dict[str, Any]) -> str:
    """Render a record as a Telegram message body.

    A tiny hashtag header makes records greppable inside Telegram itself and
    lets the scanner cheaply skip unrelated messages.
    """
    record_type = data.get("record_type", "unknown")
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{RECORD_MARKER} #{record_type}\n{body}"


def decode_record(text: Optional[str]) -> Optional[dict[str, Any]]:
    """Parse a Telegram message body back into a record, or ``None``."""
    if not text or RECORD_MARKER not in text:
        return None
    _, _, payload = text.partition("\n")
    payload = payload.strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class RecordChannel(abc.ABC):
    """Append-only-ish JSON record store (OWNERS / METADATA channels)."""

    @abc.abstractmethod
    async def append(self, data: dict[str, Any]) -> StoredRecord:
        """Persist a new record and return it with its message id."""

    @abc.abstractmethod
    async def update(self, message_id: int, data: dict[str, Any]) -> StoredRecord:
        """Overwrite an existing record in place."""

    @abc.abstractmethod
    async def delete(self, message_id: int) -> None:
        """Hard-delete a record."""

    @abc.abstractmethod
    async def iter_records(self) -> AsyncIterator[StoredRecord]:
        """Yield every record in the channel (used to build the index)."""

    @abc.abstractmethod
    async def get(self, message_id: int) -> Optional[StoredRecord]:
        """Fetch a single record by message id."""


class MediaChannel(abc.ABC):
    """Binary blob store (FILES channel)."""

    @abc.abstractmethod
    async def upload(
        self,
        stream: Any,
        *,
        filename: str,
        mime_type: str,
        size: Optional[int] = None,
        caption: Optional[str] = None,
    ) -> StoredMedia:
        """Upload a blob and return its pointer."""

    @abc.abstractmethod
    def iter_download(
        self, message_id: int, *, offset: int = 0, limit: Optional[int] = None
    ) -> AsyncIterator[bytes]:
        """Yield bytes of the blob starting at ``offset`` for ``limit`` bytes."""

    @abc.abstractmethod
    async def delete(self, message_id: int) -> None:
        """Remove the blob."""

    @abc.abstractmethod
    async def exists(self, message_id: int) -> bool:
        """Cheap existence probe."""
