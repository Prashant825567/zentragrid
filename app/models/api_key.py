"""API key domain + API models.

Only the *hash* of a key is ever persisted. ``ApiKeyCreated`` is the single
response that contains the plaintext secret.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.utils.ids import utc_now_iso

RECORD_TYPE_API_KEY = "api_key"


class ApiKey(BaseModel):
    """Record persisted as a JSON message in the OWNERS channel."""

    model_config = ConfigDict(extra="ignore")

    record_type: str = RECORD_TYPE_API_KEY
    key_id: str
    owner_id: str
    project_id: str
    name: Optional[str] = None
    key_hash: str
    key_hint: str = ""  # last 4 chars only, safe to display
    revoked: bool = False
    last_used_at: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def public(self) -> "ApiKeyPublic":
        return ApiKeyPublic(
            key_id=self.key_id,
            project_id=self.project_id,
            name=self.name,
            key_hint=self.key_hint,
            revoked=self.revoked,
            last_used_at=self.last_used_at,
            created_at=self.created_at,
        )


class ApiKeyPublic(BaseModel):
    key_id: str
    project_id: str
    name: Optional[str] = None
    key_hint: str
    revoked: bool
    last_used_at: Optional[str] = None
    created_at: str


class ApiKeyCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)


class ApiKeyCreated(BaseModel):
    """Returned exactly once — the plaintext key cannot be recovered later."""

    key: ApiKeyPublic
    api_key: str = Field(description="Plaintext key. Shown only at creation time.")


class ApiKeyList(BaseModel):
    keys: list[ApiKeyPublic]
