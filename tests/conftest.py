"""Test fixtures.

Every test runs against the in-memory storage backend and the insecure-token
development path, so NO production Telegram or Firebase credentials are needed.
"""

from __future__ import annotations

import base64
import json
import os

import pytest

# Environment must be set before app modules import settings.
os.environ.update(
    {
        "APP_ENV": "test",
        "STORAGE_BACKEND": "memory",
        "AUTH_ALLOW_INSECURE_TOKENS": "true",
        "API_KEY_PEPPER": "test-pepper-not-a-real-secret",
        "CORS_ORIGINS": "http://localhost:3000",
        "RATE_LIMIT_ENABLED": "false",
        "FIREBASE_PROJECT_ID": "",
        "FIREBASE_CLIENT_EMAIL": "",
        "FIREBASE_PRIVATE_KEY": "",
        "LOG_LEVEL": "WARNING",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.core.storage import build_storage, set_storage  # noqa: E402
from app.main import create_app  # noqa: E402


def make_token(
    email: str = "owner@example.com",
    uid: str = "firebase_uid_001",
    name: str = "Example Owner",
) -> str:
    """Build a development (unsigned) Firebase-shaped token."""
    claims = {
        "uid": uid,
        "email": email,
        "email_verified": True,
        "name": name,
        "picture": "https://example.com/avatar.png",
        "firebase": {"sign_in_provider": "google.com"},
    }
    raw = json.dumps(claims).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


@pytest.fixture(autouse=True)
def fresh_storage():
    """Isolate every test with a brand new in-memory storage container."""
    get_settings.cache_clear()
    limiter.reset()
    storage = build_storage()
    set_storage(storage)
    yield storage
    set_storage(None)


@pytest.fixture
def client(fresh_storage):
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def owner_headers():
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def signed_up_owner(client, owner_headers):
    """An owner with a completed profile."""
    response = client.post(
        "/v1/auth/google",
        json={"name": "Rahul", "company": "Example Startup"},
        headers=owner_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["owner"]


@pytest.fixture
def project(client, owner_headers, signed_up_owner):
    response = client.post(
        "/v1/projects", json={"name": "My Video App"}, headers=owner_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def api_key(client, owner_headers, project):
    response = client.post(
        f"/v1/projects/{project['project_id']}/keys",
        json={"name": "default"},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def api_headers(api_key):
    return {"Authorization": f"Bearer {api_key['api_key']}"}
