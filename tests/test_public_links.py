"""Public signed download links: HMAC unit tests + /dl route behaviour."""

from __future__ import annotations

import io

from app.services.public_links import sign_file_id, verify_signature

SAMPLE = b"public link payload " * 100


def upload(client, headers, name="app.apk", data=SAMPLE, content_type="application/octet-stream"):
    return client.post(
        "/v1/files",
        files={"file": (name, io.BytesIO(data), content_type)},
        headers=headers,
    )


def make_link(client, headers):
    up = upload(client, headers)
    assert up.status_code == 201, up.text
    file_id = up.json()["id"]
    resp = client.get(f"/v1/files/{file_id}/public-link", headers=headers)
    assert resp.status_code == 200, resp.text
    return file_id, resp.json()


# ------------------------------------------------------------- HMAC unit
def test_signature_is_deterministic():
    assert sign_file_id("file_abc") == sign_file_id("file_abc")


def test_verify_roundtrip():
    sig = sign_file_id("file_abc")
    assert verify_signature("file_abc", sig)


def test_verify_rejects_tampered_signature():
    sig = sign_file_id("file_abc")
    bad = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert not verify_signature("file_abc", bad)


def test_verify_rejects_wrong_file_id():
    assert not verify_signature("file_other", sign_file_id("file_abc"))


def test_verify_rejects_empty_and_none():
    assert not verify_signature("file_abc", "")
    assert not verify_signature("file_abc", None)


def test_verify_accepts_uppercase_hex():
    assert verify_signature("file_abc", sign_file_id("file_abc").upper())


# ----------------------------------------------------------- link issuer
def test_public_link_requires_api_key(client):
    resp = client.get("/v1/files/file_whatever/public-link")
    assert resp.status_code == 401


def test_public_link_shape_and_idempotence(client, api_headers):
    file_id, link = make_link(client, api_headers)
    assert link["file_id"] == file_id
    assert link["permanent"] is True
    assert link["signature"] == sign_file_id(file_id)
    assert f"/dl/{file_id}?sig=" in link["url"]
    # idempotent: same file -> same link
    again = client.get(f"/v1/files/{file_id}/public-link", headers=api_headers).json()
    assert again["url"] == link["url"]


def test_public_link_scoped_to_own_project(client, api_headers):
    from tests.test_files import second_project_key

    file_id, _ = make_link(client, api_headers)
    other = second_project_key(client)
    resp = client.get(f"/v1/files/{file_id}/public-link", headers=other)
    assert resp.status_code == 404


# ------------------------------------------------------------- /dl route
def test_public_download_streams_bytes_without_auth(client, api_headers):
    file_id, link = make_link(client, api_headers)
    resp = client.get(f"/dl/{file_id}?sig={link['signature']}")
    assert resp.status_code == 200
    assert resp.content == SAMPLE
    assert "attachment" in resp.headers["content-disposition"]
    assert "app.apk" in resp.headers["content-disposition"]
    assert resp.headers["content-length"] == str(len(SAMPLE))


def test_public_download_rejects_bad_signature(client, api_headers):
    file_id, link = make_link(client, api_headers)
    resp = client.get(f"/dl/{file_id}?sig=deadbeef" * 2)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_public_download_requires_signature(client, api_headers):
    file_id, _ = make_link(client, api_headers)
    assert client.get(f"/dl/{file_id}").status_code == 403


def test_bad_signature_404s_not_leaked_as_403_for_unknown_ids(client):
    # valid signature, unknown file -> 404 (signature checked first, but the
    # file genuinely does not exist)
    sig = sign_file_id("file_doesnotexist")
    resp = client.get(f"/dl/file_doesnotexist?sig={sig}")
    assert resp.status_code == 404


def test_public_download_after_delete_404s(client, api_headers):
    file_id, link = make_link(client, api_headers)
    assert client.delete(f"/v1/files/{file_id}", headers=api_headers).status_code == 200
    resp = client.get(f"/dl/{file_id}?sig={link['signature']}")
    assert resp.status_code == 404


def test_signature_for_other_file_does_not_cross_authorize(client, api_headers):
    file_id, _ = make_link(client, api_headers)
    foreign_sig = sign_file_id("file_someone_elses")
    resp = client.get(f"/dl/{file_id}?sig={foreign_sig}")
    assert resp.status_code == 403
