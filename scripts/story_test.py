"""The exact ZentraGrid story, end to end, against real Telegram.

    A startup builds an Instagram-like app. They need storage for their users'
    photos. They sign in to ZentraGrid with Google, generate an API key, put it
    in their app, and their app uploads content through the ZentraGrid API.

Run:  python scripts/story_test.py
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
G, R, C, B, X = "\033[92m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
results = []


def ok(cond, label, extra=""):
    cond = bool(cond)
    results.append(cond)
    print(f"    [{G}OK{X}]" if cond else f"    [{R}FAIL{X}]", label, f"-> {extra}" if extra else "")
    return cond


def step(n, title):
    print(f"\n{C}{B}{n}. {title}{X}")


def token(email, uid, name):
    claims = {"uid": uid, "email": email, "email_verified": True, "name": name,
              "firebase": {"sign_in_provider": "google.com"}}
    return base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")


def main() -> int:
    assert settings.STORAGE_BACKEND == "telegram", "Set STORAGE_BACKEND=telegram"
    photo = PHOTO.read_bytes()
    sha = hashlib.sha256(photo).hexdigest()
    stamp = time.strftime("%H%M%S")
    email = f"founder.{stamp}@example.com"

    print(f"\n{B}THE STORY: a startup building an Instagram-like app{X}")
    print(f"founder email: {email}")

    with TestClient(create_app()) as c:
        # ------------------------------------------------------------------
        step(1, "Founder opens zentragrid.com, clicks 'Continue with Google' (FIRST TIME)")
        h = {"Authorization": f"Bearer {token(email, f'uid_{stamp}', 'Prashant')}"}
        r = c.post("/v1/auth/google", json={}, headers=h)
        body = r.json()
        ok(r.status_code == 200, "backend verifies the Google token")
        ok(body["is_new_owner"] is True, "email is new -> owner record created in OWNERS channel")
        ok(body["requires_profile_completion"] is True, "frontend must now ask Name + Company")
        owner_id = body["owner"]["owner_id"]
        print(f"        owner_id = {owner_id}")

        # ------------------------------------------------------------------
        step(2, "Founder fills the profile form: name + company")
        r = c.patch("/v1/auth/me", json={"name": "Prashant", "company": "PixelGram"}, headers=h)
        ok(r.status_code == 200 and r.json()["profile_completed"], "profile saved")

        r = c.get("/v1/projects", headers=h)
        projects = r.json()["projects"]
        ok(len(projects) == 1, "a default project was auto-created", projects[0]["name"])
        project_id = projects[0]["project_id"]

        # ------------------------------------------------------------------
        step(3, "Founder logs out, comes back LATER with the SAME Google account")
        r = c.post("/v1/auth/google", json={}, headers=h)
        body = r.json()
        ok(body["is_new_owner"] is False, "recognised as existing owner")
        ok(body["requires_profile_completion"] is False, "NOT asked for name again")
        ok(body["owner"]["name"] == "Prashant", "old name loaded", body["owner"]["name"])
        ok(body["owner"]["company"] == "PixelGram", "old company loaded", body["owner"]["company"])
        ok(body["owner"]["owner_id"] == owner_id, "same owner_id, no duplicate record")

        # ------------------------------------------------------------------
        step(4, "Founder generates an API key for their app")
        r = c.post(f"/v1/projects/{project_id}/keys", json={"name": "pixelgram-prod"}, headers=h)
        created = r.json()
        api_key = created["api_key"]
        key_id = created["key"]["key_id"]
        ok(r.status_code == 201, "key created")
        ok(api_key.startswith("ZTG_live_"), "key format", api_key[:14] + "...")
        print(f"        founder puts this in their app's env + sets the backend URL")

        # ------------------------------------------------------------------
        step(5, "PixelGram app uploads a user's photo using that key")
        app_headers = {"Authorization": f"Bearer {api_key}"}
        r = c.post("/v1/files",
                   files={"file": ("user_42_selfie.jpg", photo, "image/jpeg")},
                   data={"metadata": json.dumps({"app_user_id": "42", "post_id": "post_991"})},
                   headers=app_headers)
        ok(r.status_code == 201, "upload accepted", f"HTTP {r.status_code}")
        file_id = r.json()["id"]
        print(f"        file_id = {file_id}")

        # ------------------------------------------------------------------
        step(6, "A request with a FAKE key must be rejected")
        r = c.post("/v1/files", files={"file": ("hack.jpg", photo, "image/jpeg")},
                   headers={"Authorization": "Bearer ZTG_live_fake_key_not_generated"})
        ok(r.status_code == 401, "unknown key -> 401", r.json()["error"]["code"])

        r = c.post("/v1/files", files={"file": ("hack.jpg", photo, "image/jpeg")})
        ok(r.status_code == 401, "no key at all -> 401")

        # ------------------------------------------------------------------
        step(7, "Metadata records WHO uploaded it (key, owner, project, file)")
        r = c.get(f"/v1/files/{file_id}", headers=app_headers)
        m = r.json()
        ok(m["id"] == file_id, "file_id", m["id"])
        ok(m["owner_id"] == owner_id, "owner_id", m["owner_id"])
        ok(m["project_id"] == project_id, "project_id", m["project_id"])
        ok(m["uploaded_by_key_id"] == key_id, "uploaded_by_key_id (which key sent it)", m["uploaded_by_key_id"])
        ok(m["name"] == "user_42_selfie.jpg", "filename", m["name"])
        ok(m["mime_type"] == "image/jpeg", "mime_type", m["mime_type"])
        ok(m["size"] == len(photo), "size", f"{m['size']:,}")
        ok(m["metadata"]["app_user_id"] == "42", "app's own custom metadata kept")
        ok(m["created_at"] and m["updated_at"], "timestamps present")
        ok("telegram" not in r.text.lower(), "Telegram internals hidden from the app")

        # ------------------------------------------------------------------
        step(8, "PixelGram serves that photo back to its user")
        r = c.get(f"/v1/files/{file_id}/download", headers=app_headers)
        ok(hashlib.sha256(r.content).hexdigest() == sha, "downloaded bytes identical to original")
        r = c.get(f"/v1/files/{file_id}/stream", headers={**app_headers, "Range": "bytes=0-2047"})
        ok(r.status_code == 206, "range request works (video seeking)", r.headers.get("content-range"))

        # ------------------------------------------------------------------
        step(9, "A DIFFERENT startup cannot touch PixelGram's files")
        h2 = {"Authorization": f"Bearer {token(f'other.{stamp}@example.com', f'uid_o_{stamp}', 'Rival')}"}
        c.post("/v1/auth/google", json={}, headers=h2)
        c.patch("/v1/auth/me", json={"name": "Rival", "company": "RivalApp"}, headers=h2)
        p2 = c.get("/v1/projects", headers=h2).json()["projects"][0]["project_id"]
        k2 = c.post(f"/v1/projects/{p2}/keys", json={}, headers=h2).json()["api_key"]
        rival = {"Authorization": f"Bearer {k2}"}
        ok(c.get(f"/v1/files/{file_id}", headers=rival).status_code == 404, "rival cannot read the file")
        ok(c.delete(f"/v1/files/{file_id}", headers=rival).status_code == 404, "rival cannot delete it")
        ok(c.get(f"/v1/files", headers=rival).json()["files"] == [], "rival sees an empty file list")

        # ------------------------------------------------------------------
        step(10, "Founder checks usage in the dashboard")
        u = c.get(f"/v1/projects/{project_id}/usage", headers=h).json()
        ok(u["total_files"] == 1, "total_files", u["total_files"])
        ok(u["total_bytes"] == len(photo), "total_bytes", f"{u['total_bytes']:,}")
        ok(u["uploads"] == 1 and u["downloads"] >= 1, "upload/download counters")
        print(f"        quota: {u['bytes_remaining']:,} bytes remaining of {u['quota_bytes']:,}")

        # ------------------------------------------------------------------
        step(11, "Founder revokes the key (say it leaked)")
        c.delete(f"/v1/projects/{project_id}/keys/{key_id}", headers=h)
        r = c.post("/v1/files", files={"file": ("x.jpg", photo, "image/jpeg")}, headers=app_headers)
        ok(r.status_code == 401, "old key stops working immediately", r.json()["error"]["code"])

        r = c.post(f"/v1/projects/{project_id}/keys", json={"name": "rotated"}, headers=h)
        new_key = {"Authorization": f"Bearer {r.json()['api_key']}"}
        ok(c.get(f"/v1/files/{file_id}", headers=new_key).status_code == 200,
           "new key works, old files still reachable")

        # cleanup so the FILES channel does not accumulate test data
        c.delete(f"/v1/files/{file_id}", headers=new_key)

    passed, total = sum(results), len(results)
    print(f"\n{C}{'=' * 62}{X}")
    print(f"  {B}{passed}/{total} checks passed{X}")
    print(f"{C}{'=' * 62}{X}\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
