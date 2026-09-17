"""File metadata domain + API models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.utils.ids import utc_now_iso

RECORD_TYPE_FILE = "file"

STATUS_ACTIVE = "active"
STATUS_DELETED = "deleted"


class FileRecord(BaseModel):
    """Record persisted as a JSON message in the METADATA channel.

    ``telegram_message_id`` is an internal pointer and is never serialised into
    an API response.
    """

    model_config = ConfigDict(extra="ignore")

    record_type: str = RECORD_TYPE_FILE
    file_id: str
    owner_id: str
    project_id: str
    filename: str
    mime_type: str
    size: int
    status: str = STATUS_ACTIVE
    telegram_message_id: Optional[int] = None
    # Which API key performed the upload. Answers "kis key se aayi thi?"
    uploaded_by_key_id: Optional[str] = None
    checksum: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def public(self) -> "FilePublic":
        return FilePublic(
            id=self.file_id,
            name=self.filename,
            project_id=self.project_id,
            owner_id=self.owner_id,
            mime_type=self.mime_type,
            size=self.size,
            status=self.status,
            uploaded_by_key_id=self.uploaded_by_key_id,
            metadata=self.metadata,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class FilePublic(BaseModel):
    id: str
    name: str
    project_id: str
    owner_id: str
    mime_type: str
    size: int
    status: str
    uploaded_by_key_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class FileUploadResponse(BaseModel):
    id: str
    name: str
    size: int
    mime_type: str
    status: str


class FileRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FileList(BaseModel):
    files: list[FilePublic]
    next_cursor: Optional[str] = None


class FileDeleted(BaseModel):
    id: str
    status: str = STATUS_DELETED
    deleted: bool = True
