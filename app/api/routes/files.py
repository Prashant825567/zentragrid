"""File routes (developer API, ZentraGrid API-key authenticated).

Every handler derives the project from the API key. A ``project_id`` supplied
by the caller is never honoured.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.errors import ValidationFailedError
from app.core.security import ApiPrincipal, rate_limited, storage_dep
from app.core.storage import Storage
from app.models.file import (
    FileDeleted,
    FileList,
    FilePublic,
    FileRename,
    FileUploadResponse,
)
from app.services.file_service import FileService
from app.services.streaming_service import StreamingService

router = APIRouter(prefix="/files", tags=["files"])


def _parse_metadata(raw: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("metadata must be a valid JSON object.") from exc
    if not isinstance(parsed, dict):
        raise ValidationFailedError("metadata must be a JSON object.")
    return parsed


@router.post(
    "",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file",
)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="The file to upload"),
    filename: Optional[str] = Form(default=None, description="Override the stored filename"),
    metadata: Optional[str] = Form(default=None, description="JSON object of custom metadata"),
    principal: ApiPrincipal = Depends(rate_limited("upload")),
    storage: Storage = Depends(storage_dep),
) -> FileUploadResponse:
    declared = request.headers.get("content-length")
    record = await FileService(storage).upload(
        principal.project,
        upload_stream=file,
        filename=filename or file.filename,
        content_type=file.content_type,
        declared_size=int(declared) if declared and declared.isdigit() else None,
        metadata=_parse_metadata(metadata),
        key_id=principal.key_id,
    )
    request.state.file_id = record.file_id
    return FileUploadResponse(
        id=record.file_id,
        name=record.filename,
        size=record.size,
        mime_type=record.mime_type,
        status=record.status,
    )


@router.get("", response_model=FileList, summary="List files (simple metadata lookup)")
async def list_files(
    query: Optional[str] = Query(default=None, max_length=120, description="Filename contains"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    principal: ApiPrincipal = Depends(rate_limited("general")),
    storage: Storage = Depends(storage_dep),
) -> FileList:
    records, next_cursor = await FileService(storage).list(
        principal.project, query=query, limit=limit, cursor=cursor
    )
    return FileList(files=[r.public() for r in records], next_cursor=next_cursor)


@router.get("/{file_id}", response_model=FilePublic, summary="Get file metadata")
async def get_file(
    file_id: str,
    request: Request,
    principal: ApiPrincipal = Depends(rate_limited("general")),
    storage: Storage = Depends(storage_dep),
) -> FilePublic:
    request.state.file_id = file_id
    record = await FileService(storage).get(principal.project, file_id)
    return record.public()


@router.patch("/{file_id}", response_model=FilePublic, summary="Rename a file")
async def rename_file(
    file_id: str,
    payload: FileRename,
    request: Request,
    principal: ApiPrincipal = Depends(rate_limited("general")),
    storage: Storage = Depends(storage_dep),
) -> FilePublic:
    request.state.file_id = file_id
    record = await FileService(storage).rename(principal.project, file_id, payload.name)
    return record.public()


@router.delete("/{file_id}", response_model=FileDeleted, summary="Delete a file")
async def delete_file(
    file_id: str,
    request: Request,
    principal: ApiPrincipal = Depends(rate_limited("general")),
    storage: Storage = Depends(storage_dep),
) -> FileDeleted:
    request.state.file_id = file_id
    record = await FileService(storage).delete(principal.project, file_id)
    return FileDeleted(id=record.file_id, status=record.status)


@router.get("/{file_id}/download", summary="Download a file (streamed)")
async def download_file(
    file_id: str,
    request: Request,
    principal: ApiPrincipal = Depends(rate_limited("download")),
    storage: Storage = Depends(storage_dep),
) -> StreamingResponse:
    request.state.file_id = file_id
    record = await FileService(storage).get(principal.project, file_id)
    iterator, headers = await StreamingService(storage).download(principal.project, record)
    return StreamingResponse(iterator, media_type=record.mime_type, headers=headers)


@router.get("/{file_id}/stream", summary="Stream a file with HTTP Range support")
async def stream_file(
    file_id: str,
    request: Request,
    principal: ApiPrincipal = Depends(rate_limited("stream")),
    storage: Storage = Depends(storage_dep),
) -> StreamingResponse:
    """Range-aware endpoint intended for ``<video>`` / ``<audio>`` playback."""
    request.state.file_id = file_id
    record = await FileService(storage).get(principal.project, file_id)
    iterator, headers, status_code = await StreamingService(storage).stream(
        principal.project, record, request.headers.get("range")
    )
    return StreamingResponse(
        iterator,
        status_code=status_code,
        media_type=record.mime_type,
        headers=headers,
    )
