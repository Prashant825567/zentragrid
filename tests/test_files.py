"""File upload, metadata, rename, delete, download and Range streaming."""

from __future__ import annotations

import io

import pytest

from tests.conftest import make_token

SAMPLE = b"ZentraGrid test payload. " * 500  # ~12.5 KB


def upload(client, headers, name="video.mp4", data=SAMPLE, content_type="video/mp4", **form):
    return client.post(
        "/v1/files",
        files={"file": (name, io.BytesIO(data), content_type)},
        data=form or None,
        headers=headers,
    )


def second_project_key(client):
    """A second owner + project + key, for isolation tests."""
    token = make_token(email="other@example.com", uid="uid_other", name="Other")
    owner_headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/v1/auth/google", json={"name": "Other", "company": "Other Co"}, headers=owner_headers
    )
    project = client.post(
        "/v1/projects", json={"name": "Other App"}, headers=owner_headers
    ).json()
    key = client.post(
        f"/v1/projects/{project['project_id']}/keys", json={}, headers=owner_headers
    ).json()
    return {"Authorization": f"Bearer {key['api_key']}"}


# ------------------------------------------------------------------ upload
def test_upload_requires_api_key(client):
    response = client.post("/v1/files", files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")})
    assert response.status_code == 401


def test_upload_returns_file_record(client, api_headers):
    response = upload(client, api_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("file_")
    assert body["name"] == "video.mp4"
    assert body["size"] == len(SAMPLE)
    assert body["mime_type"] == "video/mp4"
    assert body["status"] == "active"


def test_upload_response_hides_telegram_pointer(client, api_headers):
    body = upload(client, api_headers).text
    assert "telegram" not in body.lower()
    assert "message_id" not in body


def test_upload_sanitizes_path_traversal_filename(client, api_headers):
    response = upload(client, api_headers, name="../../etc/passwd")
    assert response.status_code == 201
    assert "/" not in response.json()["name"]


def test_upload_rejects_blocked_extension(client, api_headers):
    response = upload(client, api_headers, name="malware.exe", content_type="application/x-msdownload")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE"


def test_upload_rejects_empty_file(client, api_headers):
    response = upload(client, api_headers, data=b"")
    assert response.status_code == 400


def test_upload_accepts_custom_metadata(client, api_headers):
    created = upload(client, api_headers, metadata='{"folder": "intros", "v": 2}')
    assert created.status_code == 201
    detail = client.get(f"/v1/files/{created.json()['id']}", headers=api_headers).json()
    assert detail["metadata"] == {"folder": "intros", "v": 2}


def test_upload_rejects_malformed_metadata(client, api_headers):
    response = upload(client, api_headers, metadata="not-json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_upload_updates_usage(client, api_headers, owner_headers, project):
    upload(client, api_headers)
    usage = client.get(
        f"/v1/projects/{project['project_id']}/usage", headers=owner_headers
    ).json()
    assert usage["total_files"] == 1
    assert usage["total_bytes"] == len(SAMPLE)
    assert usage["uploads"] == 1


# ---------------------------------------------------------------- metadata
def test_get_file_metadata(client, api_headers, project):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(f"/v1/files/{file_id}", headers=api_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == file_id
    assert body["project_id"] == project["project_id"]
    assert body["size"] == len(SAMPLE)
    assert body["created_at"] and body["updated_at"]


def test_invalid_file_id_returns_404(client, api_headers):
    response = client.get("/v1/files/file_does_not_exist", headers=api_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_file_listing_and_simple_query(client, api_headers):
    upload(client, api_headers, name="intro-video.mp4")
    upload(client, api_headers, name="report.pdf", content_type="application/pdf")

    all_files = client.get("/v1/files", headers=api_headers).json()
    assert len(all_files["files"]) == 2

    filtered = client.get("/v1/files?query=video", headers=api_headers).json()
    assert len(filtered["files"]) == 1
    assert filtered["files"][0]["name"] == "intro-video.mp4"


# --------------------------------------------------------------- isolation
def test_other_project_cannot_read_file(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    intruder = second_project_key(client)
    assert client.get(f"/v1/files/{file_id}", headers=intruder).status_code == 404


def test_other_project_cannot_download_file(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    intruder = second_project_key(client)
    assert client.get(f"/v1/files/{file_id}/download", headers=intruder).status_code == 404


def test_other_project_cannot_rename_file(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    intruder = second_project_key(client)
    response = client.patch(f"/v1/files/{file_id}", json={"name": "hack.mp4"}, headers=intruder)
    assert response.status_code == 404


def test_other_project_cannot_delete_file(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    intruder = second_project_key(client)
    assert client.delete(f"/v1/files/{file_id}", headers=intruder).status_code == 404
    # Original owner still has the file.
    assert client.get(f"/v1/files/{file_id}", headers=api_headers).status_code == 200


# ------------------------------------------------------------------ rename
def test_rename_updates_metadata_only(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.patch(
        f"/v1/files/{file_id}", json={"name": "new-name.mp4"}, headers=api_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "new-name.mp4"

    # Content is untouched by an application-level rename.
    downloaded = client.get(f"/v1/files/{file_id}/download", headers=api_headers)
    assert downloaded.content == SAMPLE


def test_rename_requires_authentication(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    assert client.patch(f"/v1/files/{file_id}", json={"name": "x.mp4"}).status_code == 401


def test_rename_rejects_empty_name(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.patch(f"/v1/files/{file_id}", json={"name": ""}, headers=api_headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------ delete
def test_delete_file_and_metadata_invalidation(client, api_headers, fresh_storage):
    file_id = upload(client, api_headers).json()["id"]
    response = client.delete(f"/v1/files/{file_id}", headers=api_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    assert client.get(f"/v1/files/{file_id}", headers=api_headers).status_code == 404

    record = fresh_storage.files._by_pk[file_id]  # noqa: SLF001
    assert record.status == "deleted"
    # No active metadata may point at a removed blob.
    assert record.telegram_message_id is None


def test_delete_updates_usage(client, api_headers, owner_headers, project):
    file_id = upload(client, api_headers).json()["id"]
    client.delete(f"/v1/files/{file_id}", headers=api_headers)
    usage = client.get(
        f"/v1/projects/{project['project_id']}/usage", headers=owner_headers
    ).json()
    assert usage["total_files"] == 0
    assert usage["total_bytes"] == 0


def test_delete_requires_authentication(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    assert client.delete(f"/v1/files/{file_id}").status_code == 401


# ---------------------------------------------------------------- download
def test_download_returns_exact_bytes(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(f"/v1/files/{file_id}/download", headers=api_headers)
    assert response.status_code == 200
    assert response.content == SAMPLE
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["accept-ranges"] == "bytes"


def test_download_requires_api_key(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    assert client.get(f"/v1/files/{file_id}/download").status_code == 401


# ----------------------------------------------------------------- stream
def test_stream_without_range_returns_full_body(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(f"/v1/files/{file_id}/stream", headers=api_headers)
    assert response.status_code == 200
    assert response.content == SAMPLE
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.headers["content-disposition"].startswith("inline")


def test_stream_with_range_returns_206(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(
        f"/v1/files/{file_id}/stream",
        headers={**api_headers, "Range": "bytes=0-1023"},
    )
    assert response.status_code == 206
    assert response.content == SAMPLE[:1024]
    assert response.headers["content-length"] == "1024"
    assert response.headers["content-range"] == f"bytes 0-1023/{len(SAMPLE)}"


def test_stream_mid_range(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(
        f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=1000-1999"}
    )
    assert response.status_code == 206
    assert response.content == SAMPLE[1000:2000]


def test_stream_open_ended_range(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(
        f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=100-"}
    )
    assert response.status_code == 206
    assert response.content == SAMPLE[100:]


def test_stream_suffix_range(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(
        f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=-500"}
    )
    assert response.status_code == 206
    assert response.content == SAMPLE[-500:]


def test_stream_unsatisfiable_range(client, api_headers):
    file_id = upload(client, api_headers).json()["id"]
    response = client.get(
        f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=999999999-"}
    )
    assert response.status_code == 416
    assert response.json()["error"]["code"] == "RANGE_NOT_SATISFIABLE"


def test_stream_records_bandwidth(client, api_headers, owner_headers, project):
    file_id = upload(client, api_headers).json()["id"]
    client.get(f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=0-99"})
    usage = client.get(
        f"/v1/projects/{project['project_id']}/usage", headers=owner_headers
    ).json()
    assert usage["streams"] == 1
    assert usage["bandwidth_out_bytes"] == 100


# ------------------------------------------------------------------- misc
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/files/file_nope"),
        ("patch", "/v1/files/file_nope"),
        ("delete", "/v1/files/file_nope"),
        ("get", "/v1/files/file_nope/download"),
        ("get", "/v1/files/file_nope/stream"),
    ],
)
def test_unknown_file_ids_return_consistent_errors(client, api_headers, method, path):
    call = getattr(client, method)
    response = call(path, json={"name": "x"}, headers=api_headers) if method == "patch" else call(
        path, headers=api_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"
