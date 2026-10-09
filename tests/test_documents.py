"""Document-store API tests.

Runs entirely against the in-memory backend — no Telegram credentials needed.
"""

from __future__ import annotations

import pytest

from app.core.config import settings

NOTES = "/v1/data/notes"


def _create(client, headers, data, doc_id=None):
    payload = {"data": data}
    if doc_id:
        payload["id"] = doc_id
    return client.post(NOTES, json=payload, headers=headers)


# ------------------------------------------------------------------ create
def test_create_document_returns_201_and_generated_id(client, api_headers):
    response = _create(client, api_headers, {"title": "First note"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"].startswith("doc_")
    assert body["collection"] == "notes"
    assert body["rev"] == 1
    assert body["data"] == {"title": "First note"}
    assert body["size"] > 0
    assert body["created_at"] and body["updated_at"]


def test_create_with_custom_id(client, api_headers):
    response = _create(client, api_headers, {"title": "x"}, doc_id="my-note-1")
    assert response.status_code == 201
    assert response.json()["id"] == "my-note-1"


def test_create_duplicate_id_conflicts(client, api_headers):
    _create(client, api_headers, {"a": 1}, doc_id="dup")
    response = _create(client, api_headers, {"a": 2}, doc_id="dup")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_ALREADY_EXISTS"


def test_create_rejects_reserved_id(client, api_headers):
    response = _create(client, api_headers, {"a": 1}, doc_id="query")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_rejects_bad_id_characters(client, api_headers):
    response = _create(client, api_headers, {"a": 1}, doc_id="bad id!")
    assert response.status_code == 400


def test_create_rejects_non_object_data(client, api_headers):
    response = client.post(NOTES, json={"data": [1, 2, 3]}, headers=api_headers)
    assert response.status_code == 400


def test_create_rejects_unknown_body_field(client, api_headers):
    response = client.post(
        NOTES, json={"data": {}, "project_id": "project_hack"}, headers=api_headers
    )
    assert response.status_code == 400


def test_invalid_collection_name_rejected(client, api_headers):
    response = client.post(
        "/v1/data/not valid", json={"data": {}}, headers=api_headers
    )
    assert response.status_code in (400, 404, 422)


# -------------------------------------------------------------------- read
def test_get_document(client, api_headers):
    doc_id = _create(client, api_headers, {"title": "readme"}).json()["id"]
    response = client.get(f"{NOTES}/{doc_id}", headers=api_headers)
    assert response.status_code == 200
    assert response.json()["data"] == {"title": "readme"}


def test_get_unknown_document_404(client, api_headers):
    response = client.get(f"{NOTES}/doc_does_not_exist", headers=api_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_same_id_in_two_collections_is_independent(client, api_headers):
    client.put(f"{NOTES}/shared", json={"data": {"in": "notes"}}, headers=api_headers)
    client.put(
        "/v1/data/tasks/shared", json={"data": {"in": "tasks"}}, headers=api_headers
    )
    assert client.get(f"{NOTES}/shared", headers=api_headers).json()["data"] == {
        "in": "notes"
    }
    assert client.get("/v1/data/tasks/shared", headers=api_headers).json()["data"] == {
        "in": "tasks"
    }


# ------------------------------------------------------------------- write
def test_put_creates_when_absent(client, api_headers):
    response = client.put(
        f"{NOTES}/upserted", json={"data": {"v": 1}}, headers=api_headers
    )
    assert response.status_code == 200
    assert response.json()["rev"] == 1


def test_put_replaces_and_bumps_rev(client, api_headers):
    client.put(f"{NOTES}/r", json={"data": {"a": 1, "b": 2}}, headers=api_headers)
    response = client.put(f"{NOTES}/r", json={"data": {"a": 9}}, headers=api_headers)
    assert response.status_code == 200
    assert response.json()["rev"] == 2
    # replace, not merge — "b" is gone
    assert response.json()["data"] == {"a": 9}


def test_patch_merges_nested_objects(client, api_headers):
    client.put(
        f"{NOTES}/m",
        json={"data": {"title": "t", "meta": {"pinned": False, "tags": ["a"]}}},
        headers=api_headers,
    )
    response = client.patch(
        f"{NOTES}/m", json={"data": {"meta": {"pinned": True}}}, headers=api_headers
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "title": "t",
        "meta": {"pinned": True, "tags": ["a"]},
    }


def test_patch_replaces_arrays_wholesale(client, api_headers):
    client.put(f"{NOTES}/arr", json={"data": {"t": [1, 2, 3]}}, headers=api_headers)
    response = client.patch(
        f"{NOTES}/arr", json={"data": {"t": [9]}}, headers=api_headers
    )
    assert response.json()["data"] == {"t": [9]}


def test_patch_unknown_document_404(client, api_headers):
    response = client.patch(
        f"{NOTES}/ghost", json={"data": {"a": 1}}, headers=api_headers
    )
    assert response.status_code == 404


# ----------------------------------------------------- optimistic locking
def test_expected_rev_allows_matching_write(client, api_headers):
    client.put(f"{NOTES}/cc", json={"data": {"n": 1}}, headers=api_headers)
    response = client.put(
        f"{NOTES}/cc", json={"data": {"n": 2}, "expected_rev": 1}, headers=api_headers
    )
    assert response.status_code == 200
    assert response.json()["rev"] == 2


def test_expected_rev_rejects_stale_write(client, api_headers):
    client.put(f"{NOTES}/cc", json={"data": {"n": 1}}, headers=api_headers)
    client.put(f"{NOTES}/cc", json={"data": {"n": 2}}, headers=api_headers)
    response = client.put(
        f"{NOTES}/cc", json={"data": {"n": 3}, "expected_rev": 1}, headers=api_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVISION_CONFLICT"


def test_expected_rev_on_patch(client, api_headers):
    client.put(f"{NOTES}/cp", json={"data": {"n": 1}}, headers=api_headers)
    response = client.patch(
        f"{NOTES}/cp", json={"data": {"n": 5}, "expected_rev": 99}, headers=api_headers
    )
    assert response.status_code == 409


# ------------------------------------------------------------------ delete
def test_delete_then_get_is_404(client, api_headers):
    doc_id = _create(client, api_headers, {"a": 1}).json()["id"]
    assert client.delete(f"{NOTES}/{doc_id}", headers=api_headers).status_code == 200
    assert client.get(f"{NOTES}/{doc_id}", headers=api_headers).status_code == 404


def test_delete_unknown_404(client, api_headers):
    assert client.delete(f"{NOTES}/nope", headers=api_headers).status_code == 404


def test_delete_frees_the_id_for_reuse(client, api_headers):
    _create(client, api_headers, {"a": 1}, doc_id="recycle")
    client.delete(f"{NOTES}/recycle", headers=api_headers)
    assert _create(client, api_headers, {"a": 2}, doc_id="recycle").status_code == 201


# ------------------------------------------------------------------ query
@pytest.fixture
def seeded(client, api_headers):
    rows = [
        {"title": "alpha", "views": 10, "done": True, "tags": ["x"]},
        {"title": "beta", "views": 30, "done": False, "tags": ["x", "y"]},
        {"title": "gamma", "views": 20, "done": False, "tags": ["y"]},
        {"title": "delta", "views": 5, "done": True},
    ]
    for index, row in enumerate(rows):
        assert _create(client, api_headers, row, doc_id=f"n{index}").status_code == 201
    return rows


def test_list_returns_everything(client, api_headers, seeded):
    response = client.get(NOTES, headers=api_headers)
    assert response.status_code == 200
    assert len(response.json()["documents"]) == 4


def test_filter_eq(client, api_headers, seeded):
    response = client.get(NOTES, params=[("where", "done:eq:true")], headers=api_headers)
    titles = {d["data"]["title"] for d in response.json()["documents"]}
    assert titles == {"alpha", "delta"}


def test_filter_numeric_comparison(client, api_headers, seeded):
    response = client.get(NOTES, params=[("where", "views:gte:20")], headers=api_headers)
    assert len(response.json()["documents"]) == 2


def test_filter_contains_on_array(client, api_headers, seeded):
    response = client.get(
        NOTES, params=[("where", "tags:contains:y")], headers=api_headers
    )
    assert len(response.json()["documents"]) == 2


def test_filter_exists(client, api_headers, seeded):
    response = client.get(
        NOTES, params=[("where", "tags:exists:true")], headers=api_headers
    )
    assert len(response.json()["documents"]) == 3


def test_multiple_filters_are_anded(client, api_headers, seeded):
    response = client.get(
        NOTES,
        params=[("where", "done:eq:false"), ("where", "views:gt:25")],
        headers=api_headers,
    )
    docs = response.json()["documents"]
    assert len(docs) == 1 and docs[0]["data"]["title"] == "beta"


def test_order_by_ascending(client, api_headers, seeded):
    response = client.get(NOTES, params={"order_by": "views"}, headers=api_headers)
    views = [d["data"]["views"] for d in response.json()["documents"]]
    assert views == [5, 10, 20, 30]


def test_order_by_descending(client, api_headers, seeded):
    response = client.get(
        NOTES, params={"order_by": "views", "desc": "true"}, headers=api_headers
    )
    views = [d["data"]["views"] for d in response.json()["documents"]]
    assert views == [30, 20, 10, 5]


def test_unknown_operator_is_400(client, api_headers):
    response = client.get(NOTES, params=[("where", "a:regex:b")], headers=api_headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_QUERY"


def test_too_many_filters_is_400(client, api_headers):
    params = [("where", f"f{i}:eq:1") for i in range(settings.MAX_QUERY_FILTERS + 1)]
    response = client.get(NOTES, params=params, headers=api_headers)
    assert response.status_code == 400


def test_pagination_walks_every_document_exactly_once(client, api_headers, seeded):
    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 2, "order_by": "views"}
        if cursor:
            params["cursor"] = cursor
        body = client.get(NOTES, params=params, headers=api_headers).json()
        seen.extend(d["id"] for d in body["documents"])
        cursor = body["next_cursor"]
        pages += 1
        if not cursor or pages > 10:
            break
    assert sorted(seen) == ["n0", "n1", "n2", "n3"]
    assert len(seen) == len(set(seen))


def test_query_via_post_body(client, api_headers, seeded):
    response = client.post(
        f"{NOTES}/query",
        json={
            "where": [{"field": "views", "op": "gte", "value": 20}],
            "order_by": "views",
            "desc": True,
        },
        headers=api_headers,
    )
    assert response.status_code == 200
    views = [d["data"]["views"] for d in response.json()["documents"]]
    assert views == [30, 20]


def test_query_post_rejects_unknown_operator(client, api_headers):
    response = client.post(
        f"{NOTES}/query",
        json={"where": [{"field": "a", "op": "regex", "value": "b"}]},
        headers=api_headers,
    )
    assert response.status_code == 400


def test_query_on_empty_collection_is_empty_not_404(client, api_headers):
    response = client.get("/v1/data/never-used", headers=api_headers)
    assert response.status_code == 200
    assert response.json()["documents"] == []


# ------------------------------------------------------------ collections
def test_collections_lists_only_used_names(client, api_headers):
    _create(client, api_headers, {"a": 1})
    client.put("/v1/data/tasks/t1", json={"data": {"a": 1}}, headers=api_headers)
    response = client.get("/v1/collections", headers=api_headers)
    assert response.status_code == 200
    names = {c["name"]: c["document_count"] for c in response.json()["collections"]}
    assert names == {"notes": 1, "tasks": 1}


def test_collection_disappears_when_emptied(client, api_headers):
    _create(client, api_headers, {"a": 1}, doc_id="only")
    client.delete(f"{NOTES}/only", headers=api_headers)
    response = client.get("/v1/collections", headers=api_headers)
    assert response.json()["collections"] == []


# ------------------------------------------------------- large / blob spill
def test_large_document_spills_to_blob_and_reads_back_identical(
    client, api_headers, fresh_storage
):
    big = {"title": "long note", "body": "x" * (settings.DOC_INLINE_MAX_BYTES + 5000)}
    created = _create(client, api_headers, big, doc_id="big")
    assert created.status_code == 201

    record = next(
        r for r in fresh_storage.documents._by_pk.values() if r.doc_id == "big"
    )
    assert record.storage == "blob"
    assert record.data is None
    assert record.blob_message_id is not None

    fetched = client.get(f"{NOTES}/big", headers=api_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"] == big


def test_small_document_stays_inline(client, api_headers, fresh_storage):
    _create(client, api_headers, {"a": "short"}, doc_id="small")
    record = next(
        r for r in fresh_storage.documents._by_pk.values() if r.doc_id == "small"
    )
    assert record.storage == "inline"
    assert record.blob_message_id is None


def test_blob_document_is_queryable(client, api_headers):
    _create(
        client,
        api_headers,
        {"kind": "big", "body": "y" * (settings.DOC_INLINE_MAX_BYTES + 100)},
        doc_id="bq",
    )
    response = client.get(
        NOTES, params=[("where", "kind:eq:big")], headers=api_headers
    )
    docs = response.json()["documents"]
    assert len(docs) == 1 and docs[0]["id"] == "bq"


def test_shrinking_a_blob_document_returns_it_inline(
    client, api_headers, fresh_storage
):
    _create(
        client,
        api_headers,
        {"body": "z" * (settings.DOC_INLINE_MAX_BYTES + 2000)},
        doc_id="shrink",
    )
    client.put(f"{NOTES}/shrink", json={"data": {"body": "tiny"}}, headers=api_headers)
    record = next(
        r for r in fresh_storage.documents._by_pk.values() if r.doc_id == "shrink"
    )
    assert record.storage == "inline"
    assert record.blob_message_id is None
    assert client.get(f"{NOTES}/shrink", headers=api_headers).json()["data"] == {
        "body": "tiny"
    }


def test_document_over_hard_limit_is_413(client, api_headers):
    huge = {"body": "x" * (settings.MAX_DOCUMENT_BYTES + 1024)}
    response = _create(client, api_headers, huge)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "DOCUMENT_TOO_LARGE"


# ------------------------------------------------------------- isolation
def test_api_key_cannot_read_another_projects_documents(
    client, owner_headers, api_headers, project
):
    _create(client, api_headers, {"secret": "project one"}, doc_id="x1")

    second = client.post(
        "/v1/projects", json={"name": "Second App"}, headers=owner_headers
    ).json()
    second_key = client.post(
        f"/v1/projects/{second['project_id']}/keys",
        json={"name": "k2"},
        headers=owner_headers,
    ).json()["api_key"]
    other = {"Authorization": f"Bearer {second_key}"}

    assert client.get(f"{NOTES}/x1", headers=other).status_code == 404
    assert client.get(NOTES, headers=other).json()["documents"] == []
    assert client.get("/v1/collections", headers=other).json()["collections"] == []


def test_data_endpoints_require_an_api_key(client):
    assert client.get(NOTES).status_code == 401
    assert client.post(NOTES, json={"data": {}}).status_code == 401
    assert client.get("/v1/collections").status_code == 401


def test_firebase_token_is_not_accepted_as_api_key(client, owner_headers):
    assert client.get(NOTES, headers=owner_headers).status_code == 401


def test_revoked_key_cannot_write(client, owner_headers, project, api_key, api_headers):
    client.delete(
        f"/v1/projects/{project['project_id']}/keys/{api_key['key']['key_id']}",
        headers=owner_headers,
    )
    assert _create(client, api_headers, {"a": 1}).status_code == 401
