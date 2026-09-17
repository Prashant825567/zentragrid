"""Owner repository (OWNERS channel).

Identity is keyed on the normalised Google email, with the Firebase UID as a
secondary index. This is what guarantees "never create duplicate owner records
just because the user logs in again".
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.models.owner import RECORD_TYPE_OWNER, Owner
from app.repositories.base import IndexedRecordRepository
from app.telegram.messages import RecordChannel
from app.utils.ids import new_owner_id, utc_now_iso


def normalize_email(email: str) -> str:
    return email.strip().lower()


class OwnerRepository(IndexedRecordRepository[Owner]):
    record_type = RECORD_TYPE_OWNER
    model = Owner
    primary_key = "owner_id"

    def __init__(self, channel: RecordChannel) -> None:
        super().__init__(channel)
        self._by_email: dict[str, str] = {}
        self._by_uid: dict[str, str] = {}
        # Serialises first-time owner creation so two concurrent sign-ins with
        # the same email cannot both insert a record.
        self._create_lock = asyncio.Lock()

    def _on_index(self, entity: Owner) -> None:
        self._by_email[normalize_email(entity.email)] = entity.owner_id
        if entity.firebase_uid:
            self._by_uid[entity.firebase_uid] = entity.owner_id

    def _on_deindex(self, entity: Owner) -> None:
        self._by_email.pop(normalize_email(entity.email), None)
        self._by_uid.pop(entity.firebase_uid, None)

    async def get_by_email(self, email: str) -> Optional[Owner]:
        await self.ensure_loaded()
        owner_id = self._by_email.get(normalize_email(email))
        return self._by_pk.get(owner_id) if owner_id else None

    async def get_by_firebase_uid(self, uid: str) -> Optional[Owner]:
        await self.ensure_loaded()
        owner_id = self._by_uid.get(uid)
        return self._by_pk.get(owner_id) if owner_id else None

    async def get_or_create(
        self,
        *,
        email: str,
        firebase_uid: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        picture: Optional[str] = None,
    ) -> tuple[Owner, bool]:
        """Return ``(owner, created)``.

        Lookup order is email first (the stable human identity), then Firebase
        UID. If an existing owner is found we never overwrite their stored name
        or company — the dashboard must not re-ask for those.
        """
        await self.ensure_loaded()

        async with self._create_lock:
            existing = await self.get_by_email(email) or await self.get_by_firebase_uid(
                firebase_uid
            )
            if existing:
                changed = False
                # Heal records created before the UID was known / after re-auth.
                if firebase_uid and existing.firebase_uid != firebase_uid:
                    existing.firebase_uid = firebase_uid
                    changed = True
                if picture and existing.picture != picture:
                    existing.picture = picture
                    changed = True
                if changed:
                    existing.updated_at = utc_now_iso()
                    await self.save(existing)
                return existing, False

            owner = Owner(
                owner_id=new_owner_id(),
                firebase_uid=firebase_uid,
                email=normalize_email(email),
                name=name,
                company=company,
                picture=picture,
                profile_completed=bool(name and company),
            )
            await self.create(owner)
            return owner, True

    async def update_profile(
        self, owner: Owner, *, name: str, company: Optional[str]
    ) -> Owner:
        owner.name = name
        if company is not None:
            owner.company = company
        owner.profile_completed = True
        owner.updated_at = utc_now_iso()
        return await self.save(owner)
