"""End-to-end smoke test against REAL Telegram storage.

Runs the actual FastAPI app with STORAGE_BACKEND=telegram and exercises the
full owner -> project -> API key -> upload -> read -> stream -> rename ->
delete flow using a real photo.

    python scripts/e2e_real_test.py

Requires a populated .env (never commit it).
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402

PHOTO = Path(__file__).resolve().parent.parent / "testdata" / "test_photo.jpg"

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, extra: str = "") -> bool:
    results.append((ok, label))
    print(f"  [{PASS if ok else FAIL}] {label}{(' -> ' + extra) if extra else ''}")
    return ok


def section(title: str) -> None:
    print(f"\n\033[96m=== {title} ===\033[0m")


def dev_token(email: str, uid: str, name: str) -> str:
    claims = {
        "uid": uid,
        "email": email,
        "email_verified": True,
        "name": name,
        "firebase": {"sign_in_provider": "google.com"},
    }
    raw = json.dumps(claims).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def main() -> int:
    assert settings.STORAGE_BACKEND == "telegram", "Set STORAGE_BACKEND=telegram in .env"
    assert PHOTO.exists(), f"Missing test photo at {PHOTO}"

    photo_bytes = PHOTO.read_bytes()
    photo_sha = hashlib.sha256(photo_bytes).hexdigest()
    stamp = time.strftime("%H%M%S")
    email = f"e2e.{stamp}@example.com"

    print(f"\nPhoto: {PHOTO.name}  size={len(photo_bytes):,} bytes  sha256={photo_sha[:16]}…")

    with TestClient(create_app()) as client:
        # ------------------------------------------------------- health
        section("1. HEALTH")
        r = client.get("/health")
        check(r.status_code == 200 and r.json()["status"] == "ok", "GET /health", r.json()["storage_backend"])

        r = client.get("/health/ready")
        check(r.status_code == 200, "GET /health/ready", json.dumps(r.json()["storage"]))

        # ------------------------------------- owner signup (first login)
        section("2. OWNER SIGNUP (first login -> creates record in OWNERS channel)")
        headers = {"Authorization": f"Bearer {dev_token(email, f'uid_{stamp}', 'Hari')}"}

        r = client.post("/v1/auth/google", json={}, headers=headers)
        body = r.json()
        check(r.status_code == 200, "POST /v1/auth/google", str(r.status_code))
        check(body.get("is_new_owner") is True, "is_new_owner = true")
        check(body.get("requires_profile_completion") is True, "asks for profile completion")
        owner_id = body["owner"]["owner_id"]
        print(f"      owner_id={owner_id} email={body['owner']['email']}")

        r = client.patch(
            "/v1/auth/me", json={"name": "Hari", "company": "ZentraGrid"}, headers=headers
        )
        check(r.status_code == 200 and r.json()["profile_completed"] is True, "PATCH /v1/auth/me completes profile")

        # -------------------------------- returning login (no duplicate)
        section("3. RETURNING LOGIN (must NOT duplicate, must NOT re-ask name)")
        r = client.post("/v1/auth/google", json={}, headers=headers)
        body = r.json()
        check(body["is_new_owner"] is False, "is_new_owner = false")
        check(body["requires_profile_completion"] is False, "does not ask for name again")
        check(body["owner"]["owner_id"] == owner_id, "same owner_id reused", body["owner"]["owner_id"])
        check(body["owner"]["name"] == "Hari", "stored name returned", body["owner"]["name"])

        # ------------------------------------------------------ project
        section("4. PROJECT")
        r = client.post(
            "/v1/projects", json={"name": f"E2E App {stamp}"}, headers=headers
        )
        check(r.status_code == 201, "POST /v1/projects", str(r.status_code))
        project_id = r.json()["project_id"]
        print(f"      project_id={project_id}")

        r = client.get("/v1/projects", headers=headers)
        check(any(p["project_id"] == project_id for p in r.json()["projects"]), "GET /v1/projects lists it")

        # ------------------------------------------------------ api key
        section("5. API KEY")
        r = client.post(f"/v1/projects/{project_id}/keys", json={"name": "e2e"}, headers=headers)
        check(r.status_code == 201, "POST keys", str(r.status_code))
        created = r.json()
        api_key = created["api_key"]
        key_id = created["key"]["key_id"]
        check(api_key.startswith("ZTG_live_"), "key format ZTG_live_…", api_key[:13] + "…")
        api_headers = {"Authorization": f"Bearer {api_key}"}

        r = client.get(f"/v1/projects/{project_id}/keys", headers=headers)
        check(api_key not in r.text, "plaintext key NOT retrievable after creation")

        r = client.get("/v1/files", headers={"Authorization": "Bearer ZTG_live_invalidkey"})
        check(r.status_code == 401 and r.json()["error"]["code"] == "INVALID_API_KEY", "invalid key -> 401")

        # ------------------------------------------------------- upload
        section("6. UPLOAD PHOTO -> FILES channel (real Telegram)")
        t0 = time.perf_counter()
        r = client.post(
            "/v1/files",
            files={"file": ("zentragrid-test.jpg", photo_bytes, "image/jpeg")},
            data={"metadata": json.dumps({"source": "e2e", "run": stamp})},
            headers=api_headers,
        )
        dt = time.perf_counter() - t0
        check(r.status_code == 201, "POST /v1/files", f"{r.status_code} in {dt:.2f}s")
        if r.status_code != 201:
            print("      body:", r.text[:400])
            return 1
        up = r.json()
        file_id = up["id"]
        check(up["size"] == len(photo_bytes), "size matches", f"{up['size']:,}")
        check(up["mime_type"] == "image/jpeg", "mime_type", up["mime_type"])
        check("telegram" not in r.text.lower(), "response hides Telegram internals")
        print(f"      file_id={file_id}")

        # ----------------------------------------------------- metadata
        section("7. METADATA")
        r = client.get(f"/v1/files/{file_id}", headers=api_headers)
        meta = r.json()
        check(r.status_code == 200, "GET /v1/files/{id}")
        check(meta["project_id"] == project_id, "belongs to project")
        check(meta["metadata"] == {"source": "e2e", "run": stamp}, "custom metadata persisted")
        check("telegram_message_id" not in r.text, "telegram_message_id not exposed")

        # ----------------------------------------------------- download
        section("8. DOWNLOAD (full bytes, streamed)")
        t0 = time.perf_counter()
        r = client.get(f"/v1/files/{file_id}/download", headers=api_headers)
        dt = time.perf_counter() - t0
        check(r.status_code == 200, "GET /download", f"{r.status_code} in {dt:.2f}s")
        got_sha = hashlib.sha256(r.content).hexdigest()
        check(got_sha == photo_sha, "SHA-256 matches original (byte-perfect)", got_sha[:16] + "…")
        out = PHOTO.parent / "downloaded_from_telegram.jpg"
        out.write_bytes(r.content)
        print(f"      saved -> {out}")

        # ------------------------------------------------------- stream
        section("9. STREAM + HTTP RANGE")
        r = client.get(f"/v1/files/{file_id}/stream", headers=api_headers)
        check(r.status_code == 200 and r.content == photo_bytes, "full stream 200")
        check(r.headers.get("accept-ranges") == "bytes", "Accept-Ranges: bytes")

        r = client.get(f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=0-1023"})
        check(r.status_code == 206, "Range bytes=0-1023 -> 206")
        check(r.content == photo_bytes[:1024], "first 1 KiB exact")
        check(r.headers.get("content-range") == f"bytes 0-1023/{len(photo_bytes)}", "Content-Range header", r.headers.get("content-range"))

        mid_start, mid_end = 50_000, 60_000
        r = client.get(f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": f"bytes={mid_start}-{mid_end}"})
        check(r.status_code == 206 and r.content == photo_bytes[mid_start:mid_end + 1], "mid-file range exact (seek works)")

        r = client.get(f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=-2048"})
        check(r.status_code == 206 and r.content == photo_bytes[-2048:], "suffix range bytes=-2048")

        r = client.get(f"/v1/files/{file_id}/stream", headers={**api_headers, "Range": "bytes=999999999-"})
        check(r.status_code == 416, "unsatisfiable range -> 416")

        # ------------------------------------------------------- rename
        section("10. RENAME")
        r = client.patch(f"/v1/files/{file_id}", json={"name": "renamed-photo.jpg"}, headers=api_headers)
        check(r.status_code == 200 and r.json()["name"] == "renamed-photo.jpg", "PATCH renames in METADATA")
        r = client.get(f"/v1/files/{file_id}/download", headers=api_headers)
        check(hashlib.sha256(r.content).hexdigest() == photo_sha, "content unchanged after rename")

        # -------------------------------------------------------- usage
        section("11. USAGE")
        r = client.get(f"/v1/projects/{project_id}/usage", headers=headers)
        u = r.json()
        check(r.status_code == 200, "GET /usage")
        check(u["total_files"] == 1, "total_files = 1")
        check(u["total_bytes"] == len(photo_bytes), "total_bytes matches", f"{u['total_bytes']:,}")
        print(f"      uploads={u['uploads']} downloads={u['downloads']} streams={u['streams']} bandwidth={u['bandwidth_out_bytes']:,}")

        # ---------------------------------------------------- isolation
        section("12. PROJECT ISOLATION")
        other_h = {"Authorization": f"Bearer {dev_token(f'other.{stamp}@example.com', f'uid_o_{stamp}', 'Other')}"}
        client.post("/v1/auth/google", json={"name": "Other", "company": "Other Co"}, headers=other_h)
        r2 = client.post("/v1/projects", json={"name": f"Other {stamp}"}, headers=other_h)
        op = r2.json()["project_id"]
        ok2 = client.post(f"/v1/projects/{op}/keys", json={}, headers=other_h).json()["api_key"]
        r = client.get(f"/v1/files/{file_id}", headers={"Authorization": f"Bearer {ok2}"})
        check(r.status_code == 404, "other project cannot read file -> 404")
        r = client.get(f"/v1/projects/{project_id}/usage", headers=other_h)
        check(r.status_code == 404, "other owner cannot read usage -> 404")

        # ------------------------------------------------- key revocation
        section("13. KEY REVOCATION")
        r = client.delete(f"/v1/projects/{project_id}/keys/{key_id}", headers=headers)
        check(r.status_code == 200 and r.json()["revoked"] is True, "DELETE key")
        r = client.get(f"/v1/files/{file_id}", headers=api_headers)
        check(r.status_code == 401 and r.json()["error"]["code"] == "REVOKED_API_KEY", "revoked key -> 401")

        # ------------------------------------------------------- delete
        section("14. DELETE FILE (removes Telegram message)")
        r = client.post(f"/v1/projects/{project_id}/keys", json={"name": "e2e2"}, headers=headers)
        api_headers = {"Authorization": f"Bearer {r.json()['api_key']}"}
        r = client.delete(f"/v1/files/{file_id}", headers=api_headers)
        check(r.status_code == 200 and r.json()["status"] == "deleted", "DELETE /v1/files/{id}")
        r = client.get(f"/v1/files/{file_id}", headers=api_headers)
        check(r.status_code == 404, "deleted file -> 404")
        r = client.get(f"/v1/projects/{project_id}/usage", headers=headers)
        check(r.json()["total_files"] == 0 and r.json()["total_bytes"] == 0, "usage decremented")

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n\033[96m{'=' * 60}\033[0m")
    print(f"  RESULT: {passed}/{total} checks passed")
    if passed != total:
        print("  Failed:")
        for ok, label in results:
            if not ok:
                print(f"    - {label}")
    print(f"\033[96m{'=' * 60}\033[0m\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
