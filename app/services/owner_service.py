"""Owner sign-up / sign-in logic.

Implements the exact behaviour requested:

FIRST LOGIN  -> email absent in OWNERS channel -> create record, ask for
                name + company, ``requires_profile_completion = True``.
SECOND LOGIN -> email present -> reuse stored name/company, never re-ask,
                never create a duplicate record.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.auth.firebase import FirebaseIdentity
from app.core.storage import Storage
from app.models.owner import GoogleAuthResponse, Owner
from app.utils.ids import utc_now_iso

logger = logging.getLogger("zentragrid.services.owner")


class OwnerService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def authenticate_google(
        self,
        identity: FirebaseIdentity,
        *,
        name: Optional[str] = None,
        company: Optional[str] = None,
    ) -> GoogleAuthResponse:
        """Resolve a verified Google identity to a single owner record."""
        # ``name``/``company`` are only ever used when the record is CREATED.
        # For a returning owner the stored profile always wins over whatever
        # Google (or the client) reports, so the dashboard never re-asks.
        owner, created = await self._storage.owners.get_or_create(
            email=identity.email,
            firebase_uid=identity.uid,
            name=name or identity.name,
            company=company,
            picture=identity.picture,
        )

        # Allow an owner whose signup was interrupted to finish it here.
        if not owner.profile_completed and (name or company):
            owner = await self._complete_if_possible(owner, name, company)

        logger.info(
            "owner_authenticated owner_id=%s new=%s profile_completed=%s",
            owner.owner_id,
            created,
            owner.profile_completed,
        )

        return GoogleAuthResponse(
            owner=owner.public(),
            is_new_owner=created,
            requires_profile_completion=not owner.profile_completed,
        )

    async def _complete_if_possible(
        self, owner: Owner, name: Optional[str], company: Optional[str]
    ) -> Owner:
        effective_name = name or owner.name
        effective_company = company or owner.company
        if not effective_name:
            return owner
        owner.name = effective_name
        owner.company = effective_company
        owner.profile_completed = bool(effective_name and effective_company)
        owner.updated_at = utc_now_iso()
        return await self._storage.owners.save(owner)

    async def complete_profile(self, owner: Owner, *, name: str, company: Optional[str]) -> Owner:
        """Explicit profile completion step for a brand new owner."""
        return await self._storage.owners.update_profile(owner, name=name, company=company)

    async def get_profile(self, owner: Owner) -> Owner:
        return owner
