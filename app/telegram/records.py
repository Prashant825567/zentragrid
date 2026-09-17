"""Telegram-backed implementation of :class:`RecordChannel`.

Structured records are stored as plain-text JSON messages inside a private
channel. Editing a record edits the message in place, so a record keeps a
stable message id for its whole lifetime.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from app.core.errors import StorageBackendError
from app.telegram.client import get_client, resolve_entity
from app.telegram.messages import RecordChannel, StoredRecord, decode_record, encode_record

logger = logging.getLogger("zentragrid.telegram.records")


class TelegramRecordChannel(RecordChannel):
    def __init__(self, channel_id: str, label: str) -> None:
        self._channel_id = channel_id
        self._label = label  # e.g. "owners" — safe to log, unlike the raw id

    async def _entity(self):
        return await resolve_entity(self._channel_id)

    async def append(self, data: dict[str, Any]) -> StoredRecord:
        client = await get_client()
        entity = await self._entity()
        try:
            message = await client.send_message(entity, encode_record(data))
        except Exception as exc:
            logger.error("record_append_failed channel=%s error=%s", self._label, type(exc).__name__)
            raise StorageBackendError("Failed to persist record.") from exc
        logger.info("record_appended channel=%s type=%s", self._label, data.get("record_type"))
        return StoredRecord(message_id=message.id, data=data)

    async def update(self, message_id: int, data: dict[str, Any]) -> StoredRecord:
        client = await get_client()
        entity = await self._entity()
        try:
            await client.edit_message(entity, message_id, encode_record(data))
        except Exception as exc:
            # Telegram rejects an edit when the content is byte-identical.
            if "not modified" in str(exc).lower():
                return StoredRecord(message_id=message_id, data=data)
            logger.error("record_update_failed channel=%s error=%s", self._label, type(exc).__name__)
            raise StorageBackendError("Failed to update record.") from exc
        return StoredRecord(message_id=message_id, data=data)

    async def delete(self, message_id: int) -> None:
        client = await get_client()
        entity = await self._entity()
        try:
            await client.delete_messages(entity, [message_id])
        except Exception as exc:
            logger.error("record_delete_failed channel=%s error=%s", self._label, type(exc).__name__)
            raise StorageBackendError("Failed to delete record.") from exc

    async def get(self, message_id: int) -> Optional[StoredRecord]:
        client = await get_client()
        entity = await self._entity()
        try:
            message = await client.get_messages(entity, ids=message_id)
        except Exception as exc:
            logger.error("record_get_failed channel=%s error=%s", self._label, type(exc).__name__)
            raise StorageBackendError("Failed to read record.") from exc
        if not message:
            return None
        data = decode_record(getattr(message, "message", None))
        return StoredRecord(message_id=message.id, data=data) if data else None

    async def iter_records(self) -> AsyncIterator[StoredRecord]:
        """Full channel scan — only used to warm the in-memory index."""
        client = await get_client()
        entity = await self._entity()
        try:
            async for message in client.iter_messages(entity, reverse=True):
                data = decode_record(getattr(message, "message", None))
                if data:
                    yield StoredRecord(message_id=message.id, data=data)
        except Exception as exc:
            logger.error("record_scan_failed channel=%s error=%s", self._label, type(exc).__name__)
            raise StorageBackendError("Failed to scan records.") from exc
