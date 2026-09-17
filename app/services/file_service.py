"""File lifecycle: upload, read, rename, delete.

Uploads are spooled to a temporary file on disk (never fully buffered in RAM)
so multi-GB videos work on a small Render instance.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, BinaryIO, Optional

from app.core.config import settings
from app.core.errors import FileNotFoundError_, InvalidFileError, PayloadTooLargeError
from app.core.storage import Storage
from app.models.file import FileRecord
from app.models.project import Project
from app.services.usage_service import UsageService
from app.utils.hashing import sha256_hex
from app.utils.ids import new_file_id
from app.utils.validators import (
    guess_mime_type,
    sanitize_filename,
    validate_metadata,
    validate_upload,
)

logger = logging.getLogger("zentragrid.services.file")

SPOOL_CHUNK = 1024 * 1024  # 1 MiB read window


class FileService:
    def __init__(self, storage: Storage, usage: Optional[UsageService] = None) -> None:
        self._storage = storage
        self._usage = usage or UsageService(storage)

    # -------------------------------------------------------------- upload
    async def upload(
        self,
        project: Project,
        *,
        upload_stream: BinaryIO,
        filename: Optional[str],
        content_type: Optional[str],
        declared_size: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> FileRecord:
        safe_name = sanitize_filename(filename)
        mime_type = guess_mime_type(safe_name, content_type)
        clean_metadata = validate_metadata(metadata)
        validate_upload(safe_name, mime_type, declared_size)

        if declared_size and declared_size > settings.MAX_UPLOAD_BYTES:
            raise PayloadTooLargeError(
                f"Maximum upload size is {settings.MAX_UPLOAD_BYTES} bytes."
            )
        await self._usage.assert_can_store(project, declared_size or 0)

        tmp_path, size, checksum = await self._spool_to_disk(upload_stream)
        try:
            if size == 0:
                raise InvalidFileError("The uploaded file is empty.")
            await self._usage.assert_can_store(project, size)

            stored = await self._storage.media.upload(
                tmp_path,
                filename=safe_name,
                mime_type=mime_type,
                size=size,
                # Caption is a human breadcrumb inside Telegram; no secrets.
                caption=f"project={project.project_id} name={safe_name}",
            )

            record = FileRecord(
                file_id=new_file_id(),
                owner_id=project.owner_id,
                project_id=project.project_id,
                filename=safe_name,
                mime_type=mime_type,
                size=stored.size or size,
                telegram_message_id=stored.message_id,
                checksum=checksum,
                metadata=clean_metadata,
            )
            await self._storage.files.create(record)
            await self._usage.record_upload(project, record.size)

            logger.info(
                "file_uploaded project_id=%s file_id=%s size=%s",
                project.project_id,
                record.file_id,
                record.size,
            )
            return record
        finally:
            _safe_unlink(tmp_path)

    async def _spool_to_disk(self, stream: BinaryIO) -> tuple[str, int, str]:
        """Stream the upload to a temp file, enforcing the size cap as we go."""
        import hashlib

        digest = hashlib.sha256()
        size = 0
        fd, tmp_path = tempfile.mkstemp(prefix="zg_upload_")
        try:
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = await _read_chunk(stream, SPOOL_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > settings.MAX_UPLOAD_BYTES:
                        raise PayloadTooLargeError(
                            f"Maximum upload size is {settings.MAX_UPLOAD_BYTES} bytes."
                        )
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception:
            _safe_unlink(tmp_path)
            raise
        return tmp_path, size, digest.hexdigest()

    # ---------------------------------------------------------------- read
    async def get(self, project: Project, file_id: str) -> FileRecord:
        record = await self._storage.files.get_for_project(file_id, project.project_id)
        if record is None:
            raise FileNotFoundError_()
        return record

    async def list(
        self,
        project: Project,
        *,
        query: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> tuple[list[FileRecord], Optional[str]]:
        return await self._storage.files.list_for_project(
            project.project_id, query=query, limit=limit, cursor=cursor
        )

    # -------------------------------------------------------------- mutate
    async def rename(self, project: Project, file_id: str, new_name: str) -> FileRecord:
        """Application-level rename. The stored Telegram media is untouched."""
        record = await self.get(project, file_id)
        safe_name = sanitize_filename(new_name)
        validate_upload(safe_name, record.mime_type, record.size)
        record = await self._storage.files.rename(record, safe_name)
        await self._usage.record_request(project)
        logger.info("file_renamed project_id=%s file_id=%s", project.project_id, file_id)
        return record

    async def delete(self, project: Project, file_id: str) -> FileRecord:
        """Delete the blob first, then invalidate metadata.

        Order matters: if blob deletion fails we keep the metadata intact so we
        never end up with an orphaned, unreachable object.
        """
        record = await self.get(project, file_id)
        size = record.size

        if record.telegram_message_id is not None:
            try:
                await self._storage.media.delete(record.telegram_message_id)
            except Exception:
                logger.warning(
                    "media_delete_failed_marking_metadata project_id=%s file_id=%s",
                    project.project_id,
                    file_id,
                )

        record = await self._storage.files.mark_deleted(record)
        await self._usage.record_delete(project, size)
        logger.info("file_deleted project_id=%s file_id=%s", project.project_id, file_id)
        return record


async def _read_chunk(stream: Any, size: int) -> bytes:
    """Read from either an async (Starlette UploadFile) or sync file object."""
    read = getattr(stream, "read", None)
    if read is None:  # pragma: no cover
        raise InvalidFileError("Unsupported upload stream.")
    result = read(size)
    if hasattr(result, "__await__"):
        return await result
    return result


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:  # pragma: no cover
        pass
