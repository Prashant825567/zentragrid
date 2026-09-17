"""Project isolation, API key issuance, validation and revocation."""

from __future__ import annotations

from tests.conftest import make_token


def other_owner_headers(client):
    token = make_token(email="other@example.com", uid="uid_other", name="Other")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/v1/auth/google", json={"name": "Other", "company": "Other Co"}, headers=headers
    )
    return headers


# ---------------------------------------------------------------- projects
def test_create_and_list_projects(client, owner_headers, signed_up_owner):
    created = client.post(
        "/v1/projects", json={"name": "My Video App"}, headers=owner_headers
    )
    assert created.status_code == 201
    assert created.json()["owner_id"] == signed_up_owner["owner_id"]

    listed = client.get("/v1/projects", headers=owner_headers)
    assert listed.status_code == 200
    assert len(listed.json()["projects"]) == 1


def test_duplicate_project_name_conflicts(client, owner_headers, project):
    response = client.post(
        "/v1/projects", json={"name": "My Video App"}, headers=owner_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_owner_cannot_read_another_owners_project(client, owner_headers, project):
    intruder = other_owner_headers(client)
    response = client.get(f"/v1/projects/{project['project_id']}", headers=intruder)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_delete_project_revokes_its_keys(client, owner_headers, project, api_key, api_headers):
    deleted = client.delete(f"/v1/projects/{project['project_id']}", headers=owner_headers)
    assert deleted.status_code == 204

    # The API key must stop working immediately.
    response = client.get("/v1/files", headers=api_headers)
    assert response.status_code == 401


def test_client_supplied_owner_id_is_ignored(client, owner_headers, signed_up_owner):
    response = client.post(
        "/v1/projects",
        json={"name": "Spoofed", "owner_id": "owner_somebody_else"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert response.json()["owner_id"] == signed_up_owner["owner_id"]


# ---------------------------------------------------------------- api keys
def test_api_key_is_returned_once_and_stored_hashed(client, api_key, fresh_storage):
    plaintext = api_key["api_key"]
    assert plaintext.startswith("ZTG_live_")
    assert api_key["key"]["key_hint"] == plaintext[-4:]

    stored = list(fresh_storage.api_keys._by_pk.values())  # noqa: SLF001
    assert len(stored) == 1
    assert plaintext not in stored[0].key_hash
    assert not hasattr(stored[0], "api_key")


def test_listing_keys_never_exposes_plaintext(client, owner_headers, project, api_key):
    response = client.get(f"/v1/projects/{project['project_id']}/keys", headers=owner_headers)
    assert response.status_code == 200
    body = response.text
    assert api_key["api_key"] not in body
    assert response.json()["keys"][0]["key_id"] == api_key["key"]["key_id"]


def test_valid_api_key_authenticates(client, api_headers):
    response = client.get("/v1/files", headers=api_headers)
    assert response.status_code == 200


def test_invalid_api_key_is_rejected(client):
    response = client.get(
        "/v1/files", headers={"Authorization": "Bearer ZTG_live_totally_invalid"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_API_KEY"


def test_firebase_token_cannot_be_used_as_api_key(client, owner_headers):
    response = client.get("/v1/files", headers=owner_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_API_KEY"


def test_revoked_api_key_is_rejected(client, owner_headers, project, api_key, api_headers):
    revoked = client.delete(
        f"/v1/projects/{project['project_id']}/keys/{api_key['key']['key_id']}",
        headers=owner_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True

    response = client.get("/v1/files", headers=api_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REVOKED_API_KEY"


def test_owner_cannot_revoke_another_owners_key(client, project, api_key):
    intruder = other_owner_headers(client)
    response = client.delete(
        f"/v1/projects/{project['project_id']}/keys/{api_key['key']['key_id']}",
        headers=intruder,
    )
    assert response.status_code == 404


def test_usage_endpoint_returns_quota(client, owner_headers, project):
    response = client.get(f"/v1/projects/{project['project_id']}/usage", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 0
    assert body["quota_bytes"] > 0
