"""Dashboard authentication routes (Firebase Google Sign-In)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.auth.firebase import FirebaseIdentity
from app.core.security import get_current_owner, get_firebase_identity, storage_dep
from app.core.storage import Storage
from app.models.owner import (
    GoogleAuthRequest,
    GoogleAuthResponse,
    Owner,
    OwnerProfileUpdate,
    OwnerPublic,
)
from app.services.owner_service import OwnerService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/google",
    response_model=GoogleAuthResponse,
    summary="Sign in or sign up with a Firebase Google ID token",
)
async def google_auth(
    payload: GoogleAuthRequest = Body(default=GoogleAuthRequest()),
    identity: FirebaseIdentity = Depends(get_firebase_identity),
    storage: Storage = Depends(storage_dep),
) -> GoogleAuthResponse:
    """Verify the Firebase ID token and resolve it to exactly one owner record.

    * Email not in the OWNERS channel -> a record is created and
      ``requires_profile_completion`` is ``true`` (ask for name + company).
    * Email already present -> the stored profile is returned as-is; the name
      is never requested again and no duplicate record is created.
    """
    service = OwnerService(storage)
    return await service.authenticate_google(
        identity, name=payload.name, company=payload.company
    )


@router.get("/me", response_model=OwnerPublic, summary="Current owner profile")
async def me(owner: Owner = Depends(get_current_owner)) -> OwnerPublic:
    return owner.public()


@router.patch(
    "/me",
    response_model=OwnerPublic,
    summary="Complete or update the owner profile (first-time signup step)",
)
async def update_profile(
    payload: OwnerProfileUpdate,
    owner: Owner = Depends(get_current_owner),
    storage: Storage = Depends(storage_dep),
) -> OwnerPublic:
    service = OwnerService(storage)
    updated = await service.complete_profile(
        owner, name=payload.name, company=payload.company
    )
    return updated.public()
