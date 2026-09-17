"""Upload demo files to the real FILES channel and LEAVE THEM THERE.

Unlike scripts/e2e_real_test.py (which cleans up after itself), this script
keeps everything so you can open the Telegram channels and see the data.

    python scripts/demo_keep.py
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

ROOT = Path(__file__).resolve().parent.parent
PHOTO = ROOT / "testdata" / "test_photo.jpg"

OK = "\033[92mOK\033[0m"
INFO = "\033[96m"
END = "\033[0m"


def dev_token(email: str, uid: str, name: str) -> str:
    claims = {
        "uid": uid,
        "email": email,
        "email_verified": True,
        "name": name,
        "firebase": {"sign_in_provider": "google.com"},
    }
    return base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")


def main() -> int:
    assert settings.STORAGE_BACKEND == "telegram", "Set STORAGE_BACKEND=telegram in .env"
    assert PHOTO.exists(), f"Missing {PHOTO}"

    photo = PHOTO.read_bytes()
    sha = hashlib.sha256(photo).hexdigest()
    stamp = time.strftime("%H%M%S")

    # A small text file too, so the channel shows more than one kind of object.
    note = (
        f"ZentraGrid demo upload\n"
        f"created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"This file lives inside a private Telegram channel.\n"
    ).encode()

    with TestClient(create_app()) as client:
        print(f"\n{INFO}--- owner + project + key ---{END}")
        headers = {"Authorization": f"Bearer {dev_token(f'demo.{stamp}@example.com', f'uid_demo_{stamp}', 'Hari')}"}
        client.post("/v1/auth/google", json={"name": "Hari", "company": "ZentraGrid"}, headers=headers)
        project_id = client.post(
            "/v1/projects", json={"name": f"Demo Gallery {stamp}"}, headers=headers
        ).json()["project_id"]
        created = client.post(
            f"/v1/projects/{project_id}/keys", json={"name": "demo"}, headers=headers
        ).json()
        api_key = created["api_key"]
        api_headers = {"Authorization": f"Bearer {api_key}"}
        print(f"  [{OK}] project_id = {project_id}")
        print(f"  [{OK}] api_key    = {api_key[:16]}… (shown once)")

        print(f"\n{INFO}--- uploading to FILES channel (kept, NOT deleted) ---{END}")
        uploaded = []

        r = client.post(
            "/v1/files",
            files={"file": ("zentragrid-demo-photo.jpg", photo, "image/jpeg")},
            data={"metadata": json.dumps({"kind": "demo", "run": stamp})},
            headers=api_headers,
        )
        assert r.status_code == 201, r.text
        uploaded.append(r.json())
        print(f"  [{OK}] photo  -> file_id={r.json()['id']}  {r.json()['size']:,} bytes")

        r = client.post(
            "/v1/files",
            files={"file": ("zentragrid-readme.txt", note, "text/plain")},
            headers=api_headers,
        )
        assert r.status_code == 201, r.text
        uploaded.append(r.json())
        print(f"  [{OK}] text   -> file_id={r.json()['id']}  {r.json()['size']:,} bytes")

        print(f"\n{INFO}--- verifying round trip ---{END}")
        photo_id = uploaded[0]["id"]
        got = client.get(f"/v1/files/{photo_id}/download", headers=api_headers).content
        print(f"  [{OK}] download sha256 matches original: {hashlib.sha256(got).hexdigest() == sha}")

        r = client.get(f"/v1/files/{photo_id}/stream", headers={**api_headers, "Range": "bytes=0-1023"})
        print(f"  [{OK}] range request -> {r.status_code} {r.headers.get('content-range')}")

        r = client.get("/v1/files", headers=api_headers)
        print(f"  [{OK}] files listed in project: {len(r.json()['files'])}")

        u = client.get(f"/v1/projects/{project_id}/usage", headers=headers).json()
        print(f"  [{OK}] usage: {u['total_files']} files, {u['total_bytes']:,} bytes stored")

    print(f"\n{INFO}================================================{END}")
    print("  Files are now LIVE in your FILES channel.")
    print("  Open Telegram -> 'ZentraGrid storage' to see them.")
    print(f"{INFO}================================================{END}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
