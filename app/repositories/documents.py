"""Document repository (DATA channel).

Documents are keyed by ``project_id/collection/doc_id`` so the same document id
can safely exist in two different collections — or in two different projects —
without ever colliding. Project isolation is enforced here, in the key itself,
rather than being left to callers to remember.

Secondary indexes maintained in process:

``_by_collection``
    ``(project_id, collection) -> {composite_key}`` — powers listing and
    queries without scanning the channel.
``_blob_bodies``
    Lazily populated cache of spilled document bodies, so a large document is
    fetched from the media channel at most once per process.
"""

from __future__ import annotations

from typing import Any, Optional

from app.models.document import RECORD_TYPE_DOCUMENT, DocumentRecord
from app.repositories.base import IndexedRecordRepository
from app.telegram.messages import RecordChannel


def composite_key(project_id: str, collection: str, doc_id: str) -> str:
    return f"{project_id}/{collection}/{doc_id}"


class DocumentRepository(IndexedRecordRepository[DocumentRecord]):
    record_type = RECORD_TYPE_DOCUMENT
    model = DocumentRecord
    primary_key = "doc_id"  # superseded by _pk(); kept for base-class parity

    def __init__(self, channel: RecordChannel) -> None:
        super().__init__(channel)
        self._by_collection: dict[tuple[str, str], set[str]] = {}
        self._by_project: dict[str, set[str]] = {}
        self._blob_bodies: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------- indexing
    def _pk(self, entity: DocumentRecord) -> str:  # type: ignore[override]
        return composite_key(entity.project_id, entity.collection, entity.doc_id)

    def _on_index(self, entity: DocumentRecord) -> None:
        key = self._pk(entity)
        self._by_collection.setdefault((entity.project_id, entity.collection), set()).add(key)
        self._by_project.setdefault(entity.project_id, set()).add(key)

    def _on_deindex(self, entity: DocumentRecord) -> None:
        key = self._pk(entity)
        bucket = self._by_collection.get((entity.project_id, entity.collection))
        if bucket:
            bucket.discard(key)
            if not bucket:
                self._by_collection.pop((entity.project_id, entity.collection), None)
        project_bucket = self._by_project.get(entity.project_id)
        if project_bucket:
            project_bucket.discard(key)
        self._blob_bodies.pop(key, None)

    # ----------------------------------------------------------- blob cache
    def cache_body(self, record: DocumentRecord, body: dict[str, Any]) -> None:
        self._blob_bodies[self._pk(record)] = body

    def cached_body(self, record: DocumentRecord) -> Optional[dict[str, Any]]:
        return self._blob_bodies.get(self._pk(record))

    def drop_cached_body(self, record: DocumentRecord) -> None:
        self._blob_bodies.pop(self._pk(record), None)

    # ---------------------------------------------------------------- reads
    async def get_doc(
        self, project_id: str, collection: str, doc_id: str
    ) -> Optional[DocumentRecord]:
        await self.ensure_loaded()
        record = self._by_pk.get(composite_key(project_id, collection, doc_id))
        if record is None or record.deleted:
            return None
        return record

    async def list_collection(self, project_id: str, collection: str) -> list[DocumentRecord]:
        await self.ensure_loaded()
        keys = self._by_collection.get((project_id, collection), set())
        return [
            self._by_pk[key]
            for key in keys
            if key in self._by_pk and not self._by_pk[key].deleted
        ]

    async def collections_for(self, project_id: str) -> list[tuple[str, int]]:
        """Distinct collection names in a project with live document counts."""
        await self.ensure_loaded()
        out: list[tuple[str, int]] = []
        for (pid, name), keys in self._by_collection.items():
            if pid != project_id:
                continue
            live = sum(
                1 for key in keys if key in self._by_pk and not self._by_pk[key].deleted
            )
            if live:
                out.append((name, live))
        out.sort(key=lambda item: item[0])
        return out

    async def count_for_project(self, project_id: str) -> int:
        await self.ensure_loaded()
        keys = self._by_project.get(project_id, set())
        return sum(1 for key in keys if key in self._by_pk and not self._by_pk[key].deleted)

    async def count_for_collection(self, project_id: str, collection: str) -> int:
        records = await self.list_collection(project_id, collection)
        return len(records)

    # --------------------------------------------------------------- writes
    async def delete_doc(self, record: DocumentRecord) -> None:
        """Hard delete — the record message is removed from the channel.

        The caller is responsible for removing any spilled blob first; this
        method only owns the record.
        """
        await self.hard_delete(self._pk(record))

    def message_id_for(self, record: DocumentRecord) -> Optional[int]:
        return self.message_id_of(self._pk(record))

    def reset_index(self) -> None:  # type: ignore[override]
        super().reset_index()
        self._by_collection.clear()
        self._by_project.clear()
        self._blob_bodies.clear()
