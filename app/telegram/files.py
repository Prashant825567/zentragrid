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
import time
from collections import OrderedDict
from typing import Any, AsyncIterator, Optional

from app.core.config import settings
from app.core.errors import FileNotFoundError_, StorageBackendError
from app.telegram.client import get_client, resolve_entity
from app.telegram.messages import MediaChannel, StoredMedia

logger = logging.getLogger("zentragrid.telegram.files")

ALIGNMENT = 4096

# ---------------------------------------------------------------- media cache
#
# Every ranged read needs the message's media object before a single byte can
# be fetched. Resolving it costs a full round-trip to Telegram (~0.2s measured),
# which a video player pays on *every* seek and buffer request.
#
# The media reference (file id + access hash) is stable for the lifetime of the
# message, so it is safe to cache. If Telegram ever rejects a stale reference we
# drop the entry and resolve once more — see ``_media_for``.
_MEDIA_CACHE: "OrderedDict[tuple[str, int], tuple[float, Any]]" = OrderedDict()
_MEDIA_CACHE_MAX = 512
_MEDIA_CACHE_TTL = 1800  # 30 minutes

# Telethon raises these when a cached file reference is no longer accepted.
_STALE_REFERENCE_MARKERS = ("FILE_REFERENCE", "FILEREF", "LOCATION_INVALID")


def _is_stale_reference(exc: Exception) -> bool:
    name = type(exc).__name__.upper()
    text = str(exc).upper()
    return any(m in name or m in text for m in _STALE_REFERENCE_MARKERS)


def _cache_get(key: "tuple[str, int]") -> Optional[Any]:
    entry = _MEDIA_CACHE.get(key)
    if entry is None:
        return None
    stored_at, media = entry
    if (time.monotonic() - stored_at) > _MEDIA_CACHE_TTL:
        _MEDIA_CACHE.pop(key, None)
        return None
    _MEDIA_CACHE.move_to_end(key)
    return media


def _cache_put(key: "tuple[str, int]", media: Any) -> None:
    _MEDIA_CACHE[key] = (time.monotonic(), media)
    _MEDIA_CACHE.move_to_end(key)
    while len(_MEDIA_CACHE) > _MEDIA_CACHE_MAX:
        _MEDIA_CACHE.popitem(last=False)


def invalidate_media_cache(label: str, message_id: int) -> None:
    """Drop a cached media reference (called after delete, or on a stale ref)."""
    _MEDIA_CACHE.pop((label, message_id), None)


def _normalise_chunk_size(value: int) -> int:
    """Telegram wants a chunk size that is a multiple of 4 KiB and divides 1 MiB."""
    allowed = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]
    for size in allowed:
        if value <= size:
            return size
    return allowed[-1]


def _pick_chunk_size(offset: int, limit: Optional[int]) -> int:
    """Choose a chunk size that suits the size of *this* read.

    Big sequential reads want the largest chunk Telegram allows (measured:
    256K=0.54 MB/s, 512K=1.40, 1M=1.56). But a player asking for 64 KB should
    not wait for a whole 1 MiB to arrive — that turns a fast seek into a slow
    one. So small reads get a small chunk, large reads get the configured max.
    """
    configured = _normalise_chunk_size(settings.TG_CHUNK_SIZE)
    if limit is None:
        return configured

    # Account for bytes discarded before ``offset`` due to 4 KiB alignment.
    needed = limit + (offset - (max(offset, 0) // ALIGNMENT) * ALIGNMENT)
    return min(configured, _normalise_chunk_size(needed))


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
    async def _media_for(self, message_id: int, *, refresh: bool) -> Any:
        """Resolve a message's media object, using the cache when possible.

        Skipping this round-trip is what makes repeated range requests (video
        seeking) fast — it is otherwise paid on every single request.
        """
        key = (self._label, message_id)
        if not refresh:
            cached = _cache_get(key)
            if cached is not None:
                return cached

        client = await get_client()
        entity = await self._entity()
        message = await client.get_messages(entity, ids=message_id)
        if not message or not getattr(message, "media", None):
            invalidate_media_cache(self._label, message_id)
            raise FileNotFoundError_("The underlying stored object no longer exists.")

        _cache_put(key, message.media)
        return message.media

    async def iter_download(
        self, message_id: int, *, offset: int = 0, limit: Optional[int] = None
    ) -> AsyncIterator[bytes]:
        """Yield ``limit`` bytes (or until EOF) starting at ``offset``."""
        client = await get_client()
        entity = await self._entity()

        media = await self._media_for(message_id, refresh=False)

        chunk_size = _pick_chunk_size(offset, limit)
        aligned_offset = (max(offset, 0) // ALIGNMENT) * ALIGNMENT
        skip = offset - aligned_offset
        remaining = limit

        def _open(media_obj: Any):
            # NOTE: Telethon's RequestIter.__aiter__ RESETS the stream, so the
            # iterator must be obtained exactly once and then driven with
            # __anext__. Using `async for` on it after a manual __anext__ would
            # silently replay the first chunk.
            return client.iter_download(
                media_obj,
                offset=aligned_offset,
                chunk_size=chunk_size,
                request_size=chunk_size,
            ).__aiter__()

        try:
            iterator = _open(media)
            try:
                first = await iterator.__anext__()
            except StopAsyncIteration:
                return
            except Exception as exc:
                if not _is_stale_reference(exc):
                    raise
                # Cached reference went stale: resolve once more and retry.
                logger.info("media_reference_refreshed message_id=%s", message_id)
                media = await self._media_for(message_id, refresh=True)
                iterator = _open(media)
                try:
                    first = await iterator.__anext__()
                except StopAsyncIteration:
                    return

            async def _chunks() -> AsyncIterator[bytes]:
                yield first
                while True:
                    try:
                        yield await iterator.__anext__()
                    except StopAsyncIteration:
                        return

            async for chunk in _chunks():
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
        invalidate_media_cache(self._label, message_id)
        logger.info("media_deleted message_id=%s", message_id)

    async def exists(self, message_id: int) -> bool:
        client = await get_client()
        entity = await self._entity()
        try:
            message = await client.get_messages(entity, ids=message_id)
        except Exception:
            return False
        return bool(message and getattr(message, "media", None))
