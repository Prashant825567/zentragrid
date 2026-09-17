"""Project domain + API models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.utils.ids import utc_now_iso

RECORD_TYPE_PROJECT = "project"


class Project(BaseModel):
    """Record persisted as a JSON message in the OWNERS channel."""

    model_config = ConfigDict(extra="ignore")

    record_type: str = RECORD_TYPE_PROJECT
    project_id: str
    owner_id: str
    name: str
    description: Optional[str] = None
    plan: str = Field(default_factory=lambda: settings.DEFAULT_PLAN)
    max_bytes: int = Field(default_factory=lambda: settings.DEFAULT_PLAN_MAX_BYTES)
    max_files: int = Field(default_factory=lambda: settings.DEFAULT_PLAN_MAX_FILES)
    deleted: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def public(self) -> "ProjectPublic":
        return ProjectPublic(**self.model_dump(exclude={"record_type", "deleted"}))


class ProjectPublic(BaseModel):
    project_id: str
    owner_id: str
    name: str
    description: Optional[str] = None
    plan: str
    max_bytes: int
    max_files: int
    created_at: str
    updated_at: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class ProjectList(BaseModel):
    projects: list[ProjectPublic]
