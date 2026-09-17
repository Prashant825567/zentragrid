"""Rate limiting, error format, header hardening and secret-handling tests."""

from __future__ import annotations

import io
import logging

import pytest

from app.core.config import settings
from app.core.ratelimit import limiter
from app.utils.hashing import hash_api_key, mask_secret, verify_api_key
from app.utils.validators import parse_range_header, sanitize_filename


# ------------------------------------------------------------ rate limiting
def test_rate_limiting_returns_429(client, api_headers, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL_PER_MIN", 3)
    limiter.reset()

    statuses = [client.get("/v1/files", headers=api_headers).status_code for _ in range(5)]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses

    limited = client.get("/v1/files", headers=api_headers)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert "retry-after" in {k.lower() for k in limited.headers}
    limiter.reset()


def test_rate_limits_are_per_api_key(client, api_headers, monkeypatch):
    from tests.test_files import second_project_key

    other = second_project_key(client)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL_PER_MIN", 2)
    limiter.reset()

    for _ in range(3):
        client.get("/v1/files", headers=api_headers)
    assert client.get("/v1/files", headers=api_headers).status_code == 429
    # A different key has its own budget.
    assert client.get("/v1/files", headers=other).status_code == 200
    limiter.reset()


# ------------------------------------------------------------- error format
def test_all_errors_use_the_same_envelope(client):
    responses = [
        client.get("/v1/files"),
        client.get("/v1/files/file_x", headers={"Authorization": "Bearer ZTG_live_bad"}),
        client.get("/v1/projects"),
    ]
    for response in responses:
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert "code" in body["error"] and "message" in body["error"]
        assert isinstance(body["error"]["code"], str)


def test_validation_error_shape(client, api_headers):
    file_id = client.post(
        "/v1/files",
        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=api_headers,
    ).json()["id"]
    response = client.patch(f"/v1/files/{file_id}", json={}, headers=api_headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_404_route_uses_error_envelope(client):
    response = client.get("/v1/definitely-not-a-route")
    assert response.status_code == 404
    assert "error" in response.json()


# ---------------------------------------------------------------- headers
def test_security_headers_present(client):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]


def test_cors_allows_configured_origin_only(client):
    allowed = client.options(
        "/v1/projects",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    blocked = client.options(
        "/v1/projects",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") is None


# ------------------------------------------------------------ secret safety
def test_api_key_hashing_roundtrip():
    plaintext = "ZTG_live_abcdef123456"
    digest = hash_api_key(plaintext)
    assert digest != plaintext
    assert len(digest) == 64
    assert verify_api_key(plaintext, digest)
    assert not verify_api_key("ZTG_live_wrong", digest)


def test_mask_secret_hides_body():
    masked = mask_secret("ZTG_live_supersecretvalue1234")
    assert "supersecret" not in masked
    assert masked.endswith("1234")


def test_secrets_are_never_logged(client, api_key, api_headers, caplog):
    with caplog.at_level(logging.INFO):
        client.get("/v1/files", headers=api_headers)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert api_key["api_key"] not in logged


def test_openapi_does_not_leak_channel_ids(client):
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    body = schema.text.lower()
    assert "tg_session" not in body
    assert "tg_api_hash" not in body


# ------------------------------------------------------------- unit helpers
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Windows\\evil.txt", "evil.txt"),
        ("normal file (1).mp4", "normal file (1).mp4"),
        ("", "file.bin"),
        (None, "file.bin"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize(
    "header,size,expected",
    [
        ("bytes=0-499", 1000, (0, 499)),
        ("bytes=500-", 1000, (500, 999)),
        ("bytes=-200", 1000, (800, 999)),
        ("bytes=0-99999", 1000, (0, 999)),
        (None, 1000, None),
        ("invalid", 1000, None),
    ],
)
def test_parse_range_header(header, size, expected):
    assert parse_range_header(header, size) == expected


def test_parse_range_header_unsatisfiable():
    with pytest.raises(ValueError):
        parse_range_header("bytes=5000-", 1000)
