"""Owner domain + API models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.utils.ids import utc_now_iso

RECORD_TYPE_OWNER = "owner"


class Owner(BaseModel):
    """Record persisted as a JSON message in the OWNERS channel."""

    model_config = ConfigDict(extra="ignore")

    record_type: str = RECORD_TYPE_OWNER
    owner_id: str
    firebase_uid: str
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None
    picture: Optional[str] = None
    plan: str = "free"
    profile_completed: bool = False
    disabled: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def public(self) -> "OwnerPublic":
        return OwnerPublic(
            owner_id=self.owner_id,
            email=self.email,
            name=self.name,
            company=self.company,
            picture=self.picture,
            plan=self.plan,
            profile_completed=self.profile_completed,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class OwnerPublic(BaseModel):
    owner_id: str
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None
    picture: Optional[str] = None
    plan: str
    profile_completed: bool
    created_at: str
    updated_at: str


class GoogleAuthRequest(BaseModel):
    """Optional profile fields sent on the very first sign-in."""

    name: Optional[str] = Field(default=None, max_length=120)
    company: Optional[str] = Field(default=None, max_length=160)


class GoogleAuthResponse(BaseModel):
    owner: OwnerPublic
    is_new_owner: bool
    requires_profile_completion: bool


class OwnerProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company: Optional[str] = Field(default=None, max_length=160)
