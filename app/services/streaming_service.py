"""Download & HTTP Range streaming.

Bytes flow Telegram -> chunk -> socket. Nothing is buffered whole in RAM, so a
4 GB video streams fine on a 512 MB instance.

Range support maps ``Range: bytes=start-end`` onto Telethon's offset-based
``iter_download``, which is exactly what a browser's ``<video>`` element needs
for seeking.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional
from urllib.parse import quote

from app.core.errors import FileNotFoundError_, RangeNotSatisfiableError
from app.core.storage import Storage
from app.models.file import FileRecord
from app.models.project import Project
from app.services.usage_service import UsageService
from app.utils.validators import parse_range_header

logger = logging.getLogger("zentragrid.services.streaming")

# Cap a single range response so one client cannot pin a whole worker on a
# multi-GB request. Players simply issue the next range.
MAX_RANGE_CHUNK = 16 * 1024 * 1024  # 16 MiB

INLINE_SAFE_TYPES = ("video/", "audio/", "image/")


class StreamingService:
    def __init__(self, storage: Storage, usage: Optional[UsageService] = None) -> None:
        self._storage = storage
        self._usage = usage or UsageService(storage)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def content_disposition(filename: str, inline: bool) -> str:
        disposition = "inline" if inline else "attachment"
        ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "file"
        return (
            f"{disposition}; filename=\"{ascii_name}\"; "
            f"filename*=UTF-8''{quote(filename, safe='')}"
        )

    def _pointer(self, record: FileRecord) -> int:
        if record.telegram_message_id is None:
            raise FileNotFoundError_("The stored object for this file is no longer available.")
        return record.telegram_message_id

    async def _iterate(
        self, record: FileRecord, project: Project, *, offset: int, limit: Optional[int], stream: bool
    ) -> AsyncIterator[bytes]:
        sent = 0
        try:
            async for chunk in self._storage.media.iter_download(
                self._pointer(record), offset=offset, limit=limit
            ):
                sent += len(chunk)
                yield chunk
        finally:
            # Usage is recorded on whatever was actually delivered, even if the
            # client disconnected mid-stream.
            try:
                if stream:
                    await self._usage.record_stream(project, sent)
                else:
                    await self._usage.record_download(project, sent)
            except Exception:  # pragma: no cover
                logger.warning("usage_record_failed file_id=%s", record.file_id)

    # ----------------------------------------------------------- download
    async def download(self, project: Project, record: FileRecord) -> tuple[AsyncIterator[bytes], dict]:
        headers = {
            "Content-Length": str(record.size),
            "Content-Disposition": self.content_disposition(record.filename, inline=False),
            "Accept-Ranges": "bytes",
            "X-File-Id": record.file_id,
        }
        iterator = self._iterate(record, project, offset=0, limit=None, stream=False)
        return iterator, headers

    # ------------------------------------------------------------- stream
    async def stream(
        self, project: Project, record: FileRecord, range_header: Optional[str]
    ) -> tuple[AsyncIterator[bytes], dict, int]:
        """Return ``(iterator, headers, status_code)`` honouring ``Range``."""
        size = record.size
        inline = record.mime_type.startswith(INLINE_SAFE_TYPES)

        base_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": record.mime_type,
            "Content-Disposition": self.content_disposition(record.filename, inline=inline),
            "X-File-Id": record.file_id,
        }

        try:
            parsed = parse_range_header(range_header, size)
        except ValueError as exc:
            raise RangeNotSatisfiableError(
                "The requested range is invalid.",
                details={"size": size},
            ) from exc

        if parsed is None:
            headers = {**base_headers, "Content-Length": str(size)}
            iterator = self._iterate(record, project, offset=0, limit=None, stream=True)
            return iterator, headers, 200

        start, end = parsed
        end = min(end, start + MAX_RANGE_CHUNK - 1, size - 1)
        length = end - start + 1

        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        }
        iterator = self._iterate(record, project, offset=start, limit=length, stream=True)
        return iterator, headers, 206
