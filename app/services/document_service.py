"""Document-store business logic.

Responsibilities that deliberately live here rather than in the repository:

*   deciding whether a document is stored inline or spilled to a blob,
*   enforcing size and per-project document quotas,
*   optimistic concurrency (``expected_rev``) and per-document serialisation,
*   running queries against the in-memory index.

The service never imports Telethon. It only talks to ``Storage``, which is the
same seam every other service uses, so the document store survives a backend
swap untouched.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any, Optional

from app.core.config import settings
from app.core.errors import (
    DocumentExistsError,
    DocumentNotFoundError,
    DocumentQuotaExceededError,
    DocumentTooLargeError,
    InvalidDocumentError,
    RevisionConflictError,
    StorageBackendError,
)
from app.core.storage import Storage
from app.models.document import (
    DOCUMENT_ID_RE,
    RESERVED_DOCUMENT_IDS,
    STORAGE_BLOB,
    STORAGE_INLINE,
    DocumentRecord,
)
from app.models.project import Project
from app.utils import query as q
from app.utils.ids import new_id, utc_now_iso

logger = logging.getLogger("zentragrid.documents")

#: Serialises concurrent writes to the same document within one process.
#: Cross-process safety still relies on ``expected_rev``.
_DOC_LOCKS: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    lock = _DOC_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _DOC_LOCKS[key] = lock
    return lock


def new_document_id() -> str:
    return new_id("doc", 20)


def encode_body(data: dict[str, Any]) -> bytes:
    """Serialise a document body, rejecting anything JSON cannot represent."""
    try:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvalidDocumentError("Document contains values that are not JSON encodable.") from exc


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``patch`` into ``base``.

    Nested objects merge; every other value replaces. ``null`` stores an
    explicit null rather than deleting, matching JSON Merge Patch's *absence*
    semantics being unavailable over a typed body.
    """
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class DocumentService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    # ------------------------------------------------------------- helpers
    def _validate_doc_id(self, doc_id: str) -> str:
        if not DOCUMENT_ID_RE.match(doc_id) or doc_id in RESERVED_DOCUMENT_IDS:
            raise InvalidDocumentError(
                "Document id may only contain letters, digits, '-' and '_' (max 64 chars)."
            )
        return doc_id

    async def _load_body(self, record: DocumentRecord) -> dict[str, Any]:
        """Return a document body regardless of where it physically lives."""
        if record.is_inline:
            return record.data or {}

        cached = self._storage.documents.cached_body(record)
        if cached is not None:
            return cached

        if record.blob_message_id is None:
            raise StorageBackendError("Document body pointer is missing.")

        chunks: list[bytes] = []
        async for chunk in self._storage.media.iter_download(record.blob_message_id):
            chunks.append(chunk)
        raw = b"".join(chunks)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageBackendError("Stored document body is corrupt.") from exc
        if not isinstance(body, dict):
            raise StorageBackendError("Stored document body is not an object.")

        self._storage.documents.cache_body(record, body)
        return body

    async def _write_body(
        self, record: DocumentRecord, data: dict[str, Any]
    ) -> tuple[DocumentRecord, Optional[int]]:
        """Place ``data`` inline or in a blob and return the stale blob id."""
        encoded = encode_body(data)
        size = len(encoded)

        if size > settings.MAX_DOCUMENT_BYTES:
            raise DocumentTooLargeError(
                f"Document is {size} bytes; the maximum is {settings.MAX_DOCUMENT_BYTES}."
            )

        previous_blob = record.blob_message_id
        record.size = size

        if size <= settings.DOC_INLINE_MAX_BYTES:
            record.storage = STORAGE_INLINE
            record.data = data
            record.blob_message_id = None
            self._storage.documents.drop_cached_body(record)
            return record, previous_blob

        stored = await self._storage.media.upload(
            io.BytesIO(encoded),
            filename=f"{record.doc_id}.json",
            mime_type="application/json",
            size=size,
            caption=f"#zg_doc {record.collection}",
        )
        record.storage = STORAGE_BLOB
        record.data = None
        record.blob_message_id = stored.message_id
        self._storage.documents.cache_body(record, data)
        return record, previous_blob

    async def _drop_blob(self, message_id: Optional[int]) -> None:
        if message_id is None:
            return
        try:
            await self._storage.media.delete(message_id)
        except Exception:  # noqa: BLE001 - orphaned blob must never fail a write
            logger.warning("document_blob_cleanup_failed message_id=%s", message_id)

    async def _enforce_quota(self, project: Project) -> None:
        count = await self._storage.documents.count_for_project(project.project_id)
        if count >= settings.DEFAULT_PLAN_MAX_DOCUMENTS:
            raise DocumentQuotaExceededError(
                f"This project already holds {count} documents "
                f"(limit {settings.DEFAULT_PLAN_MAX_DOCUMENTS})."
            )

    @staticmethod
    def _check_rev(record: DocumentRecord, expected_rev: Optional[int]) -> None:
        if expected_rev is not None and record.rev != expected_rev:
            raise RevisionConflictError(
                f"Document is at revision {record.rev}, not {expected_rev}."
            )

    # ---------------------------------------------------------------- CRUD
    async def create(
        self,
        project: Project,
        collection: str,
        data: dict[str, Any],
        *,
        doc_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> tuple[DocumentRecord, dict[str, Any]]:
        """Create a document. Fails if ``doc_id`` is given and already taken."""
        await self._enforce_quota(project)
        resolved_id = self._validate_doc_id(doc_id) if doc_id else new_document_id()

        key = f"{project.project_id}/{collection}/{resolved_id}"
        async with _lock_for(key):
            existing = await self._storage.documents.get_doc(
                project.project_id, collection, resolved_id
            )
            if existing is not None:
                raise DocumentExistsError(
                    f"Document '{resolved_id}' already exists in '{collection}'."
                )

            record = DocumentRecord(
                doc_id=resolved_id,
                collection=collection,
                project_id=project.project_id,
                owner_id=owner_id or project.owner_id,
            )
            record, _ = await self._write_body(record, data)
            await self._storage.documents.create(record)

        logger.info(
            "document_created project=%s collection=%s storage=%s size=%s",
            project.project_id,
            collection,
            record.storage,
            record.size,
        )
        return record, data

    async def set(
        self,
        project: Project,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        expected_rev: Optional[int] = None,
        owner_id: Optional[str] = None,
    ) -> tuple[DocumentRecord, dict[str, Any]]:
        """Create or fully replace a document (idempotent upsert)."""
        self._validate_doc_id(doc_id)
        key = f"{project.project_id}/{collection}/{doc_id}"

        async with _lock_for(key):
            record = await self._storage.documents.get_doc(
                project.project_id, collection, doc_id
            )
            if record is None:
                if expected_rev is not None:
                    raise DocumentNotFoundError()
                await self._enforce_quota(project)
                record = DocumentRecord(
                    doc_id=doc_id,
                    collection=collection,
                    project_id=project.project_id,
                    owner_id=owner_id or project.owner_id,
                )
                record, _ = await self._write_body(record, data)
                await self._storage.documents.create(record)
                return record, data

            self._check_rev(record, expected_rev)
            record.rev += 1
            record.updated_at = utc_now_iso()
            record, stale_blob = await self._write_body(record, data)
            await self._storage.documents.save(record)

        if stale_blob is not None and stale_blob != record.blob_message_id:
            await self._drop_blob(stale_blob)
        return record, data

    async def merge(
        self,
        project: Project,
        collection: str,
        doc_id: str,
        patch: dict[str, Any],
        *,
        expected_rev: Optional[int] = None,
    ) -> tuple[DocumentRecord, dict[str, Any]]:
        """Recursively merge ``patch`` into an existing document."""
        self._validate_doc_id(doc_id)
        key = f"{project.project_id}/{collection}/{doc_id}"

        async with _lock_for(key):
            record = await self._storage.documents.get_doc(
                project.project_id, collection, doc_id
            )
            if record is None:
                raise DocumentNotFoundError()
            self._check_rev(record, expected_rev)

            current = await self._load_body(record)
            merged = deep_merge(current, patch)

            record.rev += 1
            record.updated_at = utc_now_iso()
            record, stale_blob = await self._write_body(record, merged)
            await self._storage.documents.save(record)

        if stale_blob is not None and stale_blob != record.blob_message_id:
            await self._drop_blob(stale_blob)
        return record, merged

    async def get(
        self, project: Project, collection: str, doc_id: str
    ) -> tuple[DocumentRecord, dict[str, Any]]:
        record = await self._storage.documents.get_doc(
            project.project_id, collection, doc_id
        )
        if record is None:
            raise DocumentNotFoundError()
        return record, await self._load_body(record)

    async def delete(self, project: Project, collection: str, doc_id: str) -> None:
        key = f"{project.project_id}/{collection}/{doc_id}"
        async with _lock_for(key):
            record = await self._storage.documents.get_doc(
                project.project_id, collection, doc_id
            )
            if record is None:
                raise DocumentNotFoundError()
            blob_id = record.blob_message_id
            await self._storage.documents.delete_doc(record)
        await self._drop_blob(blob_id)
        logger.info(
            "document_deleted project=%s collection=%s", project.project_id, collection
        )

    # --------------------------------------------------------------- query
    async def query(
        self,
        project: Project,
        collection: str,
        *,
        filters: Optional[list[tuple[str, str, Any]]] = None,
        order_by: Optional[str] = None,
        desc: bool = False,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> tuple[list[tuple[DocumentRecord, dict[str, Any]]], Optional[str]]:
        """Filter, sort and paginate a collection.

        Inline documents are matched straight from the index. Blob-backed
        documents must be fetched to be filtered, which is the price of storing
        a body too large for one record — so keep queried fields small.
        """
        filters = filters or []
        records = await self._storage.documents.list_collection(
            project.project_id, collection
        )

        needs_body = bool(filters) or bool(order_by)

        def sort_value(record: DocumentRecord, body: dict[str, Any]) -> Any:
            """The value this document is ordered by."""
            if not order_by:
                return record.created_at
            value = q.resolve_path(body, order_by)
            return None if value is q.MISSING else value

        def full_key(record: DocumentRecord, body: dict[str, Any]):
            return (q.sort_key(sort_value(record, body)), record.doc_id)

        pairs: list[tuple[DocumentRecord, dict[str, Any]]] = []
        for record in records:
            if record.is_inline:
                body = record.data or {}
            elif needs_body:
                body = await self._load_body(record)
            else:
                body = {}
            if filters and not q.matches_all(body, filters):
                continue
            pairs.append((record, body))

        pairs.sort(key=lambda pair: full_key(*pair), reverse=desc)

        decoded = q.decode_cursor(cursor) if cursor else None
        if decoded is not None:
            anchor = (q.sort_key(decoded[0]), decoded[1])
            if desc:
                pairs = [pair for pair in pairs if full_key(*pair) < anchor]
            else:
                pairs = [pair for pair in pairs if full_key(*pair) > anchor]

        limit = max(1, min(limit, 200))
        page = pairs[:limit]
        next_cursor = None
        if len(pairs) > limit and page:
            last_record, last_body = page[-1]
            next_cursor = q.encode_cursor(
                sort_value(last_record, last_body), last_record.doc_id
            )

        # Blob bodies are only materialised when a filter or sort needed them.
        hydrated: list[tuple[DocumentRecord, dict[str, Any]]] = []
        for record, body in page:
            if not record.is_inline and not needs_body:
                body = await self._load_body(record)
            hydrated.append((record, body))
        return hydrated, next_cursor

    async def collections(self, project: Project) -> list[tuple[str, int]]:
        return await self._storage.documents.collections_for(project.project_id)

    async def count(self, project: Project, collection: str) -> int:
        return await self._storage.documents.count_for_collection(
            project.project_id, collection
        )
