"""Document-store routes (developer API, ZentraGrid API-key authenticated).

A Firestore-shaped JSON datastore:

=========================================  ==================================
``POST   /v1/data/{collection}``           create a document (auto id)
``GET    /v1/data/{collection}``           list / filter / sort / paginate
``POST   /v1/data/{collection}/query``     the same, as a JSON body
``GET    /v1/data/{collection}/{id}``      read one document
``PUT    /v1/data/{collection}/{id}``      create or fully replace
``PATCH  /v1/data/{collection}/{id}``      recursive merge
``DELETE /v1/data/{collection}/{id}``      delete
``GET    /v1/collections``                 collections in this project
=========================================  ==================================

As everywhere else in the developer API, the project is derived from the API
key. A ``project_id`` supplied by the caller is never honoured, so one
customer's key can never read another customer's collections.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.errors import InvalidQueryError, ValidationFailedError
from app.core.security import ApiPrincipal, rate_limited, storage_dep
from app.core.storage import Storage
from app.models.document import (
    COLLECTION_RE,
    CollectionInfo,
    CollectionList,
    DocumentDeleted,
    DocumentList,
    DocumentPublic,
    DocumentQuery,
    DocumentWrite,
)
from app.services.document_service import DocumentService
from app.utils import query as q

router = APIRouter(tags=["data"])


def valid_collection(
    collection: str = Path(..., description="Collection name", max_length=64),
) -> str:
    if not COLLECTION_RE.match(collection):
        raise ValidationFailedError(
            "Collection names may only contain letters, digits, '-' and '_' "
            "(max 64 chars) and must start with a letter or digit."
        )
    return collection


def _parse_filters(expressions: list[str]) -> list[tuple]:
    from app.core.config import settings

    if len(expressions) > settings.MAX_QUERY_FILTERS:
        raise InvalidQueryError(
            f"At most {settings.MAX_QUERY_FILTERS} filters may be combined."
        )
    try:
        return q.parse_where(expressions)
    except ValueError as exc:
        raise InvalidQueryError(str(exc)) from exc


# --------------------------------------------------------------- collections
@router.get(
    "/collections",
    response_model=CollectionList,
    summary="List collections in this project",
)
async def list_collections(
    principal: ApiPrincipal = Depends(rate_limited("data_read")),
    storage: Storage = Depends(storage_dep),
) -> CollectionList:
    pairs = await DocumentService(storage).collections(principal.project)
    return CollectionList(
        collections=[CollectionInfo(name=name, document_count=count) for name, count in pairs]
    )


# ----------------------------------------------------------------- documents
@router.post(
    "/data/{collection}",
    response_model=DocumentPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a document",
)
async def create_document(
    payload: DocumentWrite,
    collection: str = Depends(valid_collection),
    principal: ApiPrincipal = Depends(rate_limited("data_write")),
    storage: Storage = Depends(storage_dep),
) -> DocumentPublic:
    record, body = await DocumentService(storage).create(
        principal.project,
        collection,
        payload.data,
        doc_id=payload.id,
        owner_id=principal.owner_id,
    )
    return record.public(body)


@router.get(
    "/data/{collection}",
    response_model=DocumentList,
    summary="List or query documents",
)
async def list_documents(
    collection: str = Depends(valid_collection),
    where: list[str] = Query(
        default_factory=list,
        description="Filter as field:op:value, repeatable. "
        "Ops: eq, ne, lt, lte, gt, gte, in, nin, contains, starts_with, ends_with, exists.",
    ),
    order_by: Optional[str] = Query(default=None, max_length=200),
    desc: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    principal: ApiPrincipal = Depends(rate_limited("data_read")),
    storage: Storage = Depends(storage_dep),
) -> DocumentList:
    records, next_cursor = await DocumentService(storage).query(
        principal.project,
        collection,
        filters=_parse_filters(where),
        order_by=order_by,
        desc=desc,
        limit=limit,
        cursor=cursor,
    )
    return DocumentList(
        documents=[record.public(body) for record, body in records],
        next_cursor=next_cursor,
    )


@router.post(
    "/data/{collection}/query",
    response_model=DocumentList,
    summary="Query documents with a JSON body",
)
async def query_documents(
    payload: DocumentQuery,
    collection: str = Depends(valid_collection),
    principal: ApiPrincipal = Depends(rate_limited("data_read")),
    storage: Storage = Depends(storage_dep),
) -> DocumentList:
    from app.core.config import settings

    if len(payload.where) > settings.MAX_QUERY_FILTERS:
        raise InvalidQueryError(
            f"At most {settings.MAX_QUERY_FILTERS} filters may be combined."
        )
    unknown = [
        f.op for f in payload.where if f.op not in q.OPERATORS and f.op != "exists"
    ]
    if unknown:
        raise InvalidQueryError(
            f"Unknown operator '{unknown[0]}'. Supported: "
            + ", ".join(sorted(set(q.OPERATORS) | {"exists"}))
        )

    records, next_cursor = await DocumentService(storage).query(
        principal.project,
        collection,
        filters=[(f.field, f.op, f.value) for f in payload.where],
        order_by=payload.order_by,
        desc=payload.desc,
        limit=payload.limit,
        cursor=payload.cursor,
    )
    return DocumentList(
        documents=[record.public(body) for record, body in records],
        next_cursor=next_cursor,
    )


@router.get(
    "/data/{collection}/{doc_id}",
    response_model=DocumentPublic,
    summary="Get a document",
)
async def get_document(
    doc_id: str = Path(..., max_length=64),
    collection: str = Depends(valid_collection),
    principal: ApiPrincipal = Depends(rate_limited("data_read")),
    storage: Storage = Depends(storage_dep),
) -> DocumentPublic:
    record, body = await DocumentService(storage).get(
        principal.project, collection, doc_id
    )
    return record.public(body)


@router.put(
    "/data/{collection}/{doc_id}",
    response_model=DocumentPublic,
    summary="Create or replace a document",
)
async def set_document(
    payload: DocumentWrite,
    doc_id: str = Path(..., max_length=64),
    collection: str = Depends(valid_collection),
    principal: ApiPrincipal = Depends(rate_limited("data_write")),
    storage: Storage = Depends(storage_dep),
) -> DocumentPublic:
    record, body = await DocumentService(storage).set(
        principal.project,
        collection,
        doc_id,
        payload.data,
        expected_rev=payload.expected_rev,
        owner_id=principal.owner_id,
    )
    return record.public(body)


@router.patch(
    "/data/{collection}/{doc_id}",
    response_model=DocumentPublic,
    summary="Merge fields into a document",
)
async def merge_document(
    payload: DocumentWrite,
    doc_id: str = Path(..., max_length=64),
    collection: str = Depends(valid_collection),
    principal: ApiPrincipal = Depends(rate_limited("data_write")),
    storage: Storage = Depends(storage_dep),
) -> DocumentPublic:
    record, body = await DocumentService(storage).merge(
        principal.project,
        collection,
        doc_id,
        payload.data,
        expected_rev=payload.expected_rev,
    )
    return record.public(body)


@router.delete(
    "/data/{collection}/{doc_id}",
    response_model=DocumentDeleted,
    summary="Delete a document",
)
async def delete_document(
    doc_id: str = Path(..., max_length=64),
    collection: str = Depends(valid_collection),
    principal: ApiPrincipal = Depends(rate_limited("data_write")),
    storage: Storage = Depends(storage_dep),
) -> DocumentDeleted:
    await DocumentService(storage).delete(principal.project, collection, doc_id)
    return DocumentDeleted(id=doc_id, collection=collection)
