"""Keyless (JWKS) Firebase ID-token verification.

These tests cover the path used when no service-account key is available —
e.g. when the org policy ``iam.disableServiceAccountKeyCreation`` blocks key
downloads. They run fully offline: a throwaway RSA keypair stands in for
Google's signing key.
"""

from __future__ import annotations

import importlib
import time

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

PROJECT_ID = "zentragrid"
KID = "test-kid-1"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key, pem


@pytest.fixture
def jwks(keypair, monkeypatch):
    """Point the verifier at our fake signing key instead of Google's."""
    import app.auth.jwks as module

    importlib.reload(module)
    key, _ = keypair
    monkeypatch.setattr(module, "_fetch_jwks", lambda: {KID: key.public_key()})
    module._cached_keys = {}
    module._cached_at = 0.0
    return module


def make_token(pem, *, project=PROJECT_ID, kid=KID, alg="RS256", **overrides):
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{project}",
        "aud": project,
        "sub": "firebase_uid_123",
        "email": "owner@example.com",
        "email_verified": True,
        "name": "Example Owner",
        "iat": now,
        "exp": now + 3600,
        "firebase": {"sign_in_provider": "google.com"},
    }
    claims.update(overrides)
    return jwt.encode(claims, pem, algorithm=alg, headers={"kid": kid})


# ------------------------------------------------------------------- accept
def test_valid_token_is_accepted(jwks, keypair):
    _, pem = keypair
    claims = jwks.verify_firebase_jwt(make_token(pem), PROJECT_ID)
    assert claims["email"] == "owner@example.com"
    assert claims["uid"] == "firebase_uid_123"


def test_uid_is_derived_from_sub(jwks, keypair):
    _, pem = keypair
    claims = jwks.verify_firebase_jwt(make_token(pem, sub="abc123"), PROJECT_ID)
    assert claims["uid"] == "abc123"


# ------------------------------------------------------------------- reject
def test_token_signed_by_another_key_is_rejected(jwks):
    from app.core.errors import InvalidFirebaseTokenError

    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = attacker.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(make_token(pem), PROJECT_ID)


def test_unsigned_alg_none_is_rejected(jwks):
    from app.core.errors import InvalidFirebaseTokenError

    token = jwt.encode({"sub": "x", "aud": PROJECT_ID}, key="", algorithm="none")
    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(token, PROJECT_ID)


def test_expired_token_is_rejected(jwks, keypair):
    from app.core.errors import InvalidFirebaseTokenError

    _, pem = keypair
    now = int(time.time())
    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(
            make_token(pem, iat=now - 7200, exp=now - 3600), PROJECT_ID
        )


def test_token_for_another_project_is_rejected(jwks, keypair):
    from app.core.errors import InvalidFirebaseTokenError

    _, pem = keypair
    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(make_token(pem, project="someone-else"), PROJECT_ID)


def test_wrong_issuer_is_rejected(jwks, keypair):
    from app.core.errors import InvalidFirebaseTokenError

    _, pem = keypair
    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(
            make_token(pem, iss="https://evil.example.com/zentragrid"), PROJECT_ID
        )


def test_unknown_kid_is_rejected(jwks, keypair):
    from app.core.errors import InvalidFirebaseTokenError

    _, pem = keypair
    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(make_token(pem, kid="not-a-real-kid"), PROJECT_ID)


@pytest.mark.parametrize("bad", ["", "garbage", "a.b.c", "....."])
def test_malformed_tokens_are_rejected(jwks, bad):
    from app.core.errors import InvalidFirebaseTokenError

    with pytest.raises(InvalidFirebaseTokenError):
        jwks.verify_firebase_jwt(bad, PROJECT_ID)


def test_missing_project_id_is_a_configuration_error(jwks, keypair):
    from app.core.errors import ConfigurationError

    _, pem = keypair
    with pytest.raises(ConfigurationError):
        jwks.verify_firebase_jwt(make_token(pem), "")


# --------------------------------------------------------------- mode logic
@pytest.mark.parametrize(
    "env,expected",
    [
        ({"FIREBASE_PROJECT_ID": "p", "FIREBASE_CLIENT_EMAIL": "e@x.com",
          "FIREBASE_PRIVATE_KEY": "k", "AUTH_ALLOW_INSECURE_TOKENS": "false"}, "admin"),
        ({"FIREBASE_PROJECT_ID": "p", "FIREBASE_CLIENT_EMAIL": "",
          "FIREBASE_PRIVATE_KEY": "", "AUTH_ALLOW_INSECURE_TOKENS": "false"}, "jwks"),
        ({"FIREBASE_PROJECT_ID": "", "FIREBASE_CLIENT_EMAIL": "",
          "FIREBASE_PRIVATE_KEY": "", "AUTH_ALLOW_INSECURE_TOKENS": "true",
          "APP_ENV": "development"}, "insecure"),
        ({"FIREBASE_PROJECT_ID": "", "FIREBASE_CLIENT_EMAIL": "",
          "FIREBASE_PRIVATE_KEY": "", "AUTH_ALLOW_INSECURE_TOKENS": "false"}, "unconfigured"),
    ],
)
def test_auth_mode_resolution(env, expected, monkeypatch):
    for key in ["FIREBASE_PROJECT_ID", "FIREBASE_CLIENT_EMAIL", "FIREBASE_PRIVATE_KEY",
                "AUTH_ALLOW_INSECURE_TOKENS", "APP_ENV"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import app.core.config as config_module

    importlib.reload(config_module)
    import app.auth.firebase as firebase_module

    importlib.reload(firebase_module)
    try:
        assert firebase_module.auth_mode() == expected
    finally:
        # Restore the shared modules for the rest of the suite.
        for key in env:
            monkeypatch.delenv(key, raising=False)
        importlib.reload(config_module)
        importlib.reload(firebase_module)
