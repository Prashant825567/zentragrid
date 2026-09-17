"""File metadata repository (METADATA channel).

Keeps a per-project secondary index plus a lowercase filename index so the
future ``GET /v1/files?query=`` endpoint never has to scan Telegram.
"""

from __future__ import annotations

from typing import Optional

from app.models.file import RECORD_TYPE_FILE, STATUS_ACTIVE, STATUS_DELETED, FileRecord
from app.repositories.base import IndexedRecordRepository
from app.telegram.messages import RecordChannel
from app.utils.ids import utc_now_iso


class FileRepository(IndexedRecordRepository[FileRecord]):
    record_type = RECORD_TYPE_FILE
    model = FileRecord
    primary_key = "file_id"

    def __init__(self, channel: RecordChannel) -> None:
        super().__init__(channel)
        self._by_project: dict[str, set[str]] = {}

    def _on_index(self, entity: FileRecord) -> None:
        self._by_project.setdefault(entity.project_id, set()).add(entity.file_id)

    def _on_deindex(self, entity: FileRecord) -> None:
        bucket = self._by_project.get(entity.project_id)
        if bucket:
            bucket.discard(entity.file_id)

    async def get_for_project(self, file_id: str, project_id: str) -> Optional[FileRecord]:
        """Ownership-scoped fetch. Project isolation is enforced here."""
        record = await self.get(file_id)
        if not record or record.project_id != project_id or record.status != STATUS_ACTIVE:
            return None
        return record

    async def list_for_project(
        self,
        project_id: str,
        *,
        query: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> tuple[list[FileRecord], Optional[str]]:
        """Simple indexed listing with an opaque ``created_at`` cursor."""
        await self.ensure_loaded()
        ids = self._by_project.get(project_id, set())
        records = [
            self._by_pk[fid]
            for fid in ids
            if fid in self._by_pk and self._by_pk[fid].status == STATUS_ACTIVE
        ]

        if query:
            needle = query.strip().lower()
            records = [r for r in records if needle in r.filename.lower()]

        records.sort(key=lambda r: (r.created_at, r.file_id), reverse=True)

        if cursor:
            records = [r for r in records if f"{r.created_at}|{r.file_id}" < cursor]

        limit = max(1, min(limit, 200))
        page = records[:limit]
        next_cursor = (
            f"{page[-1].created_at}|{page[-1].file_id}" if len(records) > limit else None
        )
        return page, next_cursor

    async def mark_deleted(self, record: FileRecord) -> FileRecord:
        """Soft-delete metadata and drop the storage pointer.

        The pointer is cleared so no active metadata can ever reference a blob
        that has already been removed.
        """
        record.status = STATUS_DELETED
        record.telegram_message_id = None
        record.updated_at = utc_now_iso()
        return await self.save(record)

    async def rename(self, record: FileRecord, new_name: str) -> FileRecord:
        """Application-level rename only — the stored blob is untouched."""
        record.filename = new_name
        record.updated_at = utc_now_iso()
        return await self.save(record)

    async def count_for_project(self, project_id: str) -> int:
        await self.ensure_loaded()
        ids = self._by_project.get(project_id, set())
        return sum(
            1 for fid in ids if fid in self._by_pk and self._by_pk[fid].status == STATUS_ACTIVE
        )
