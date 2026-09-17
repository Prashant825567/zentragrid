"""In-memory storage backend.

Implements the exact same contracts as the Telegram backend so the whole API
can run (and be tested) without MTProto credentials. Selected with
``STORAGE_BACKEND=memory``. Not for production — data dies with the process.
"""

from __future__ import annotations

import asyncio
import copy
import io
import os
from typing import Any, AsyncIterator, Optional

from app.core.errors import FileNotFoundError_
from app.telegram.messages import MediaChannel, RecordChannel, StoredMedia, StoredRecord


class InMemoryRecordChannel(RecordChannel):
    def __init__(self) -> None:
        self._records: dict[int, dict[str, Any]] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def append(self, data: dict[str, Any]) -> StoredRecord:
        async with self._lock:
            message_id = self._next_id
            self._next_id += 1
            self._records[message_id] = copy.deepcopy(data)
        return StoredRecord(message_id=message_id, data=copy.deepcopy(data))

    async def update(self, message_id: int, data: dict[str, Any]) -> StoredRecord:
        async with self._lock:
            self._records[message_id] = copy.deepcopy(data)
        return StoredRecord(message_id=message_id, data=copy.deepcopy(data))

    async def delete(self, message_id: int) -> None:
        async with self._lock:
            self._records.pop(message_id, None)

    async def get(self, message_id: int) -> Optional[StoredRecord]:
        data = self._records.get(message_id)
        return StoredRecord(message_id=message_id, data=copy.deepcopy(data)) if data else None

    async def iter_records(self) -> AsyncIterator[StoredRecord]:
        for message_id in sorted(self._records):
            yield StoredRecord(message_id=message_id, data=copy.deepcopy(self._records[message_id]))


class InMemoryMediaChannel(MediaChannel):
    def __init__(self) -> None:
        self._blobs: dict[int, bytes] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def upload(
        self,
        stream: Any,
        *,
        filename: str,
        mime_type: str,
        size: Optional[int] = None,
        caption: Optional[str] = None,
    ) -> StoredMedia:
        if isinstance(stream, (str, os.PathLike)):
            with open(stream, "rb") as handle:
                payload = handle.read()
        elif isinstance(stream, (bytes, bytearray)):
            payload = bytes(stream)
        elif isinstance(stream, io.IOBase) or hasattr(stream, "read"):
            stream.seek(0)
            payload = stream.read()
        else:  # pragma: no cover
            raise TypeError(f"Unsupported stream type: {type(stream)!r}")

        async with self._lock:
            message_id = self._next_id
            self._next_id += 1
            self._blobs[message_id] = payload

        return StoredMedia(
            message_id=message_id,
            size=len(payload),
            mime_type=mime_type,
            filename=filename,
        )

    async def iter_download(
        self, message_id: int, *, offset: int = 0, limit: Optional[int] = None
    ) -> AsyncIterator[bytes]:
        blob = self._blobs.get(message_id)
        if blob is None:
            raise FileNotFoundError_("The underlying stored object no longer exists.")
        end = len(blob) if limit is None else min(offset + limit, len(blob))
        chunk_size = 64 * 1024
        for start in range(offset, end, chunk_size):
            yield blob[start : min(start + chunk_size, end)]

    async def delete(self, message_id: int) -> None:
        async with self._lock:
            self._blobs.pop(message_id, None)

    async def exists(self, message_id: int) -> bool:
        return message_id in self._blobs
