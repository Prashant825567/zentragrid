"""Firebase authentication, owner creation and returning-owner behaviour."""

from __future__ import annotations

from tests.conftest import make_token


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ZentraGrid"


def test_missing_authorization_header_is_rejected(client):
    response = client.post("/v1/auth/google", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_ID_TOKEN"


def test_invalid_firebase_token_is_rejected(client):
    response = client.post(
        "/v1/auth/google", json={}, headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_ID_TOKEN"


def test_api_key_cannot_be_used_on_dashboard_routes(client):
    response = client.get(
        "/v1/auth/me", headers={"Authorization": "Bearer ZTG_live_something"}
    )
    assert response.status_code == 401


def test_first_login_creates_owner_and_requests_profile(client):
    response = client.post(
        "/v1/auth/google", json={}, headers={"Authorization": f"Bearer {make_token()}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_new_owner"] is True
    assert body["requires_profile_completion"] is True
    assert body["owner"]["email"] == "owner@example.com"
    assert body["owner"]["owner_id"].startswith("owner_")


def test_first_login_with_profile_completes_signup(client):
    response = client.post(
        "/v1/auth/google",
        json={"name": "Rahul", "company": "Example Startup"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    body = response.json()
    assert body["is_new_owner"] is True
    assert body["requires_profile_completion"] is False
    assert body["owner"]["name"] == "Rahul"
    assert body["owner"]["company"] == "Example Startup"


def test_second_login_reuses_existing_owner_without_duplicates(client, fresh_storage):
    headers = {"Authorization": f"Bearer {make_token()}"}
    first = client.post(
        "/v1/auth/google",
        json={"name": "Rahul", "company": "Example Startup"},
        headers=headers,
    ).json()

    second = client.post("/v1/auth/google", json={}, headers=headers).json()

    assert second["is_new_owner"] is False
    assert second["requires_profile_completion"] is False
    assert second["owner"]["owner_id"] == first["owner"]["owner_id"]
    # Stored profile wins — the dashboard must not ask for the name again.
    assert second["owner"]["name"] == "Rahul"
    assert second["owner"]["company"] == "Example Startup"


def test_duplicate_email_never_creates_a_second_record(client, fresh_storage):
    headers = {"Authorization": f"Bearer {make_token()}"}
    for _ in range(4):
        client.post("/v1/auth/google", json={"name": "Rahul"}, headers=headers)

    owners = [
        record
        for record in fresh_storage.owners._by_pk.values()  # noqa: SLF001
        if record.email == "owner@example.com"
    ]
    assert len(owners) == 1


def test_email_match_wins_even_if_firebase_uid_changes(client):
    client.post(
        "/v1/auth/google",
        json={"name": "Rahul", "company": "Example Startup"},
        headers={"Authorization": f"Bearer {make_token(uid='uid_one')}"},
    )
    second = client.post(
        "/v1/auth/google",
        json={},
        headers={"Authorization": f"Bearer {make_token(uid='uid_two')}"},
    ).json()
    assert second["is_new_owner"] is False


def test_different_emails_create_different_owners(client):
    first = client.post(
        "/v1/auth/google",
        json={"name": "A"},
        headers={"Authorization": f"Bearer {make_token(email='a@example.com', uid='uid_a')}"},
    ).json()
    second = client.post(
        "/v1/auth/google",
        json={"name": "B"},
        headers={"Authorization": f"Bearer {make_token(email='b@example.com', uid='uid_b')}"},
    ).json()
    assert first["owner"]["owner_id"] != second["owner"]["owner_id"]


def test_auth_me_returns_profile(client, owner_headers, signed_up_owner):
    response = client.get("/v1/auth/me", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
    assert response.json()["name"] == "Rahul"


def test_profile_completion_endpoint(client):
    headers = {"Authorization": f"Bearer {make_token()}"}
    client.post("/v1/auth/google", json={}, headers=headers)

    response = client.patch(
        "/v1/auth/me", json={"name": "Rahul", "company": "Example Startup"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["profile_completed"] is True


def test_incomplete_profile_blocks_dashboard_resources(client):
    headers = {"Authorization": f"Bearer {make_token()}"}
    client.post("/v1/auth/google", json={}, headers=headers)

    response = client.post("/v1/projects", json={"name": "Test"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PROFILE_INCOMPLETE"


def test_unknown_owner_cannot_reach_dashboard(client):
    response = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {make_token(email='ghost@example.com', uid='ghost')}"},
    )
    assert response.status_code == 401
