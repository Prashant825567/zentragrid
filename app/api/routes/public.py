"""Public (unauthenticated) routes — signed download links.

``GET /dl/{file_id}?sig=…`` streams a file to anyone holding a valid signed
link. No API key, no Firebase token: the HMAC signature is the capability.
Mounted at the application root (not under ``/v1``) so links stay short.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.core.errors import FileNotFoundError_, ForbiddenError
from app.core.security import storage_dep
from app.core.storage import Storage
from app.models.file import STATUS_ACTIVE
from app.services.public_links import verify_signature
from app.services.streaming_service import StreamingService

router = APIRouter(tags=["public"])


@router.get("/dl/{file_id}", summary="Public download via signed link (no auth header)")
async def public_download(
    file_id: str,
    request: Request,
    sig: str = Query(default="", max_length=64, description="Link signature"),
    storage: Storage = Depends(storage_dep),
) -> StreamingResponse:
    # Signature first, storage second: an invalid signature must not reveal
    # whether the file id exists.
    if not verify_signature(file_id, sig):
        raise ForbiddenError(
            "Invalid or missing link signature.",
            code="INVALID_SIGNATURE",
        )

    request.state.file_id = file_id
    record = await storage.files.get(file_id)
    if record is None or record.status != STATUS_ACTIVE or record.telegram_message_id is None:
        raise FileNotFoundError_(f"File '{file_id}' is not available.")

    project = await storage.projects.get(record.project_id)
    if project is None:  # pragma: no cover - metadata corruption guard
        raise FileNotFoundError_(f"File '{file_id}' is not available.")

    iterator, headers = await StreamingService(storage).download(project, record)
    return StreamingResponse(iterator, media_type=record.mime_type, headers=headers)
