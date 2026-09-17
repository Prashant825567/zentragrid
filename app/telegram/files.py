"""Telegram-backed implementation of :class:`MediaChannel` (FILES channel).

Design notes
------------
* Uploads are streamed from a temporary file on disk, never buffered in RAM.
* Downloads use ``client.iter_download`` with an explicit byte offset so HTTP
  Range requests map onto Telegram's native chunked file API.
* Telegram requires 4 KiB-aligned offsets, so we align down and trim the
  leading bytes ourselves — callers can pass any arbitrary offset.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from app.core.config import settings
from app.core.errors import FileNotFoundError_, StorageBackendError
from app.telegram.client import get_client, resolve_entity
from app.telegram.messages import MediaChannel, StoredMedia

logger = logging.getLogger("zentragrid.telegram.files")

ALIGNMENT = 4096


def _normalise_chunk_size(value: int) -> int:
    """Telegram wants a chunk size that is a multiple of 4 KiB and divides 1 MiB."""
    allowed = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]
    for size in allowed:
        if value <= size:
            return size
    return allowed[-1]


class TelegramMediaChannel(MediaChannel):
    def __init__(self, channel_id: str, label: str = "files") -> None:
        self._channel_id = channel_id
        self._label = label

    async def _entity(self):
        return await resolve_entity(self._channel_id)

    # ------------------------------------------------------------- upload
    async def upload(
        self,
        stream: Any,
        *,
        filename: str,
        mime_type: str,
        size: Optional[int] = None,
        caption: Optional[str] = None,
    ) -> StoredMedia:
        """``stream`` is a filesystem path or an open binary file object."""
        from telethon.tl.types import DocumentAttributeFilename

        client = await get_client()
        entity = await self._entity()
        try:
            # Two steps on purpose: ``upload_file`` is what carries the real
            # filename onto the uploaded handle, and an explicit
            # DocumentAttributeFilename + mime_type keep Telegram from falling
            # back to our temp-file name / application-octet-stream.
            handle = await client.upload_file(
                stream,
                file_name=filename,
                part_size_kb=512,
            )
            message = await client.send_file(
                entity,
                handle,
                caption=(caption or "")[:1024],
                force_document=True,  # never let Telegram re-compress the data
                attributes=[DocumentAttributeFilename(file_name=filename)],
                mime_type=mime_type,
                supports_streaming=mime_type.startswith("video/"),
            )
        except Exception as exc:
            logger.error("media_upload_failed channel=%s error=%s", self._label, type(exc).__name__)
            raise StorageBackendError("Failed to upload file to storage.") from exc

        actual_size = size
        document = getattr(getattr(message, "media", None), "document", None)
        if document is not None and getattr(document, "size", None):
            actual_size = int(document.size)

        logger.info("media_uploaded channel=%s message_id=%s", self._label, message.id)
        return StoredMedia(
            message_id=message.id,
            size=int(actual_size or 0),
            mime_type=mime_type,
            filename=filename,
        )

    # ----------------------------------------------------------- download
    async def iter_download(
        self, message_id: int, *, offset: int = 0, limit: Optional[int] = None
    ) -> AsyncIterator[bytes]:
        """Yield ``limit`` bytes (or until EOF) starting at ``offset``."""
        client = await get_client()
        entity = await self._entity()

        message = await client.get_messages(entity, ids=message_id)
        if not message or not getattr(message, "media", None):
            raise FileNotFoundError_("The underlying stored object no longer exists.")

        chunk_size = _normalise_chunk_size(settings.TG_CHUNK_SIZE)
        aligned_offset = (max(offset, 0) // ALIGNMENT) * ALIGNMENT
        skip = offset - aligned_offset
        remaining = limit

        try:
            async for chunk in client.iter_download(
                message.media,
                offset=aligned_offset,
                chunk_size=chunk_size,
                request_size=chunk_size,
            ):
                if skip:
                    if len(chunk) <= skip:
                        skip -= len(chunk)
                        continue
                    chunk = chunk[skip:]
                    skip = 0
                if remaining is not None:
                    if remaining <= 0:
                        break
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]
                    remaining -= len(chunk)
                if chunk:
                    yield chunk
                if remaining is not None and remaining <= 0:
                    break
        except FileNotFoundError_:
            raise
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("media_download_failed message_id=%s error=%s", message_id, type(exc).__name__)
            raise StorageBackendError("Failed to read file from storage.") from exc

    # ------------------------------------------------------------- delete
    async def delete(self, message_id: int) -> None:
        client = await get_client()
        entity = await self._entity()
        try:
            await client.delete_messages(entity, [message_id])
        except Exception as exc:
            logger.error("media_delete_failed message_id=%s error=%s", message_id, type(exc).__name__)
            raise StorageBackendError("Failed to delete file from storage.") from exc
        logger.info("media_deleted message_id=%s", message_id)

    async def exists(self, message_id: int) -> bool:
        client = await get_client()
        entity = await self._entity()
        try:
            message = await client.get_messages(entity, ids=message_id)
        except Exception:
            return False
        return bool(message and getattr(message, "media", None))
