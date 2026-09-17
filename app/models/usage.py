"""Usage / quota models.

Usage is kept as a rolling summary record in the OWNERS channel (no separate
database). The shape is intentionally simple so it can be moved to Redis or a
real DB later without touching the service layer contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.utils.ids import utc_now_iso

RECORD_TYPE_USAGE = "usage"


class UsageRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    record_type: str = RECORD_TYPE_USAGE
    owner_id: str
    project_id: str
    total_files: int = 0
    total_bytes: int = 0
    uploads: int = 0
    downloads: int = 0
    streams: int = 0
    bandwidth_out_bytes: int = 0
    api_requests: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def public(self, max_bytes: int, max_files: int) -> "UsagePublic":
        return UsagePublic(
            project_id=self.project_id,
            total_files=self.total_files,
            total_bytes=self.total_bytes,
            uploads=self.uploads,
            downloads=self.downloads,
            streams=self.streams,
            bandwidth_out_bytes=self.bandwidth_out_bytes,
            api_requests=self.api_requests,
            quota_bytes=max_bytes,
            quota_files=max_files,
            bytes_remaining=max(max_bytes - self.total_bytes, 0),
            files_remaining=max(max_files - self.total_files, 0),
            updated_at=self.updated_at,
        )


class UsagePublic(BaseModel):
    project_id: str
    total_files: int
    total_bytes: int
    uploads: int
    downloads: int
    streams: int
    bandwidth_out_bytes: int
    api_requests: int
    quota_bytes: int
    quota_files: int
    bytes_remaining: int
    files_remaining: int
    updated_at: str
