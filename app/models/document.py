"""Document-store domain + API models.

A *document* is an arbitrary JSON object stored under a *collection* inside a
project — the same mental model as Firestore, minus subcollections.

Two physical layouts exist and the caller never has to care which is used:

``inline``
    The JSON fits in a single record message, so it lives in the record
    channel and is served directly from the in-memory index (no I/O at read
    time).

``blob``
    The JSON is too large for one message, so the body is spilled into the
    media channel and the record keeps only a pointer. Reads pay one fetch,
    which is then cached.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.ids import utc_now_iso

RECORD_TYPE_DOCUMENT = "document"

STORAGE_INLINE = "inline"
STORAGE_BLOB = "blob"

#: Collections and document ids are part of the public URL space, so they are
#: deliberately restricted to characters that never need escaping.
COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")

#: Reserved so a future router change can never collide with a document id.
RESERVED_DOCUMENT_IDS = frozenset({"query", "count", "batch", "index"})


class DocumentRecord(BaseModel):
    """Record persisted as a JSON message in the DATA channel."""

    model_config = ConfigDict(extra="ignore")

    record_type: str = RECORD_TYPE_DOCUMENT
    doc_id: str
    collection: str
    project_id: str
    owner_id: str

    #: Monotonic revision, bumped on every successful write. Used for
    #: optimistic concurrency so two racing writers cannot silently clobber
    #: each other.
    rev: int = 1

    storage: str = STORAGE_INLINE
    data: Optional[dict[str, Any]] = None
    blob_message_id: Optional[int] = None

    #: Size of the encoded JSON body in bytes (not the envelope).
    size: int = 0

    deleted: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @property
    def is_inline(self) -> bool:
        return self.storage == STORAGE_INLINE

    def public(self, data: dict[str, Any]) -> "DocumentPublic":
        return DocumentPublic(
            id=self.doc_id,
            collection=self.collection,
            rev=self.rev,
            size=self.size,
            created_at=self.created_at,
            updated_at=self.updated_at,
            data=data,
        )


class DocumentPublic(BaseModel):
    id: str
    collection: str
    rev: int
    size: int
    created_at: str
    updated_at: str
    data: dict[str, Any]


class DocumentList(BaseModel):
    documents: list[DocumentPublic]
    next_cursor: Optional[str] = None


class DocumentDeleted(BaseModel):
    id: str
    collection: str
    deleted: bool = True


class DocumentWrite(BaseModel):
    """Body for create / replace / merge."""

    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any] = Field(description="Arbitrary JSON object to store")
    #: Optional caller-chosen id. Ignored by PUT/PATCH (the path wins).
    id: Optional[str] = Field(default=None, max_length=64)
    #: Optimistic concurrency: reject the write unless the stored revision
    #: matches. Omit to write unconditionally.
    expected_rev: Optional[int] = Field(default=None, ge=1)

    @field_validator("data")
    @classmethod
    def _reject_non_object(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("data must be a JSON object")
        return value

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not DOCUMENT_ID_RE.match(value):
            raise ValueError(
                "id may only contain letters, digits, '-' and '_' (max 64 chars)"
            )
        if value in RESERVED_DOCUMENT_IDS:
            raise ValueError(f"'{value}' is a reserved document id")
        return value


class QueryFilter(BaseModel):
    """One ``where`` clause of a structured query."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=200)
    op: str = Field(default="eq")
    value: Any = None


class DocumentQuery(BaseModel):
    """Body of ``POST /v1/data/{collection}/query``."""

    model_config = ConfigDict(extra="forbid")

    where: list[QueryFilter] = Field(default_factory=list)
    order_by: Optional[str] = Field(default=None, max_length=200)
    desc: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    cursor: Optional[str] = None


class CollectionInfo(BaseModel):
    name: str
    document_count: int


class CollectionList(BaseModel):
    collections: list[CollectionInfo]
