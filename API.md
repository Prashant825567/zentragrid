# ZentraGrid API Reference

Base URL: `https://<your-service>.onrender.com`

Two auth schemes:

| Audience | Header | Used for |
|---|---|---|
| **Dashboard** (owner) | `Authorization: Bearer <FIREBASE_ID_TOKEN>` | auth, projects, keys, usage |
| **Developer** (app) | `Authorization: Bearer ZTG_live_...` | file operations |

---

## Route table

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Liveness probe |
| `GET` | `/health/ready` | — | Readiness (checks Telegram + Firebase) |
| `POST` | `/v1/auth/google` | Firebase | Sign in / sign up |
| `GET` | `/v1/auth/me` | Firebase | Current owner profile |
| `PATCH` | `/v1/auth/me` | Firebase | Complete/update profile |
| `POST` | `/v1/projects` | Firebase | Create project |
| `GET` | `/v1/projects` | Firebase | List projects |
| `GET` | `/v1/projects/{project_id}` | Firebase | Get project |
| `DELETE` | `/v1/projects/{project_id}` | Firebase | Delete project + revoke keys |
| `POST` | `/v1/projects/{project_id}/keys` | Firebase | Create API key |
| `GET` | `/v1/projects/{project_id}/keys` | Firebase | List keys |
| `DELETE` | `/v1/projects/{project_id}/keys/{key_id}` | Firebase | Revoke key |
| `GET` | `/v1/projects/{project_id}/usage` | Firebase | Usage + quota |
| `POST` | `/v1/files` | API key | Upload |
| `GET` | `/v1/files` | API key | List / search |
| `GET` | `/v1/files/{file_id}` | API key | Metadata |
| `PATCH` | `/v1/files/{file_id}` | API key | Rename |
| `DELETE` | `/v1/files/{file_id}` | API key | Delete |
| `GET` | `/v1/files/{file_id}/download` | API key | Download (streamed) |
| `GET` | `/v1/files/{file_id}/stream` | API key | Stream with Range support |

---

## Errors

Every error uses the same envelope:

```json
{ "error": { "code": "INVALID_API_KEY", "message": "The provided API key is invalid." } }
```

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Body/query failed validation |
| 400 | `INVALID_FILE` | Blocked extension, empty file, bad MIME |
| 401 | `INVALID_ID_TOKEN` | Firebase token missing/expired/invalid |
| 401 | `INVALID_API_KEY` | Unknown API key |
| 401 | `REVOKED_API_KEY` | Key was revoked |
| 403 | `PROFILE_INCOMPLETE` | Owner must finish signup first |
| 403 | `FORBIDDEN` | Account disabled |
| 404 | `FILE_NOT_FOUND` / `PROJECT_NOT_FOUND` / `API_KEY_NOT_FOUND` | Also returned for cross-tenant access (ids stay unenumerable) |
| 409 | `CONFLICT` | Duplicate project name, limit reached |
| 413 | `PAYLOAD_TOO_LARGE` | Over `MAX_UPLOAD_BYTES` |
| 413 | `QUOTA_EXCEEDED` | Project storage/file quota hit |
| 416 | `RANGE_NOT_SATISFIABLE` | Bad `Range` header |
| 429 | `RATE_LIMITED` | Includes `Retry-After` header |
| 500 | `INTERNAL_ERROR` | Unexpected |
| 503 | `STORAGE_UNAVAILABLE` | Telegram unreachable |

---

## Authentication

### `POST /v1/auth/google`

Verifies the Firebase ID token and resolves it to exactly one owner.

**Body** (optional, only meaningful on first signup)

```json
{ "name": "Rahul", "company": "Example Startup" }
```

**First login** — email not yet in the OWNERS channel:

```json
{
  "owner": { "owner_id": "owner_a1b2...", "email": "user@example.com",
             "name": null, "company": null, "plan": "free",
             "profile_completed": false, "created_at": "...", "updated_at": "..." },
  "is_new_owner": true,
  "requires_profile_completion": true
}
```

→ show the Name + Company form, then call `PATCH /v1/auth/me`.

**Returning login** — email already exists:

```json
{
  "owner": { "owner_id": "owner_a1b2...", "name": "Rahul",
             "company": "Example Startup", "profile_completed": true, ... },
  "is_new_owner": false,
  "requires_profile_completion": false
}
```

→ go straight to the dashboard. The name is never asked again and no duplicate
record is created, no matter how many times the user signs in.

### `GET /v1/auth/me`

Returns the owner profile.

### `PATCH /v1/auth/me`

```json
{ "name": "Rahul", "company": "Example Startup" }
```

---

## Projects

### `POST /v1/projects`

```json
{ "name": "My Video App", "description": "optional" }
```

→ `201`

```json
{ "project_id": "project_x7k2...", "owner_id": "owner_a1b2...",
  "name": "My Video App", "plan": "free",
  "max_bytes": 10737418240, "max_files": 10000,
  "created_at": "...", "updated_at": "..." }
```

`owner_id` in the body is ignored — it always comes from the verified token.
Max 50 projects per owner. Duplicate names → `409`.

### `GET /v1/projects`

```json
{ "projects": [ { ... }, { ... } ] }
```

### `DELETE /v1/projects/{project_id}`

→ `204`. Soft-deletes the project and revokes all its API keys immediately.

---

## API keys

### `POST /v1/projects/{project_id}/keys`

```json
{ "name": "production" }
```

→ `201` — **the only time the plaintext key is ever returned**

```json
{
  "key": { "key_id": "key_m3n4...", "project_id": "project_x7k2...",
           "name": "production", "key_hint": "f4c1", "revoked": false,
           "last_used_at": null, "created_at": "..." },
  "api_key": "ZTG_live_xY9kL2mNpQ7rS4tU8vW1xZ3aB6cD0eF5gH"
}
```

Store it immediately. Only an HMAC-SHA256 digest and the last 4 chars are kept
server-side. Max 20 active keys per project.

### `GET /v1/projects/{project_id}/keys`

```json
{ "keys": [ { "key_id": "key_m3n4...", "key_hint": "f4c1", "revoked": false, ... } ] }
```

### `DELETE /v1/projects/{project_id}/keys/{key_id}`

Revokes it. Subsequent use → `401 REVOKED_API_KEY`.

---

## Files

### `POST /v1/files`

`multipart/form-data`

| Field | Required | Notes |
|---|---|---|
| `file` | yes | The binary |
| `filename` | no | Override the stored name |
| `metadata` | no | JSON object, ≤32 flat keys |

```bash
curl -X POST https://api.example.com/v1/files \
  -H "Authorization: Bearer ZTG_live_xxx" \
  -F "file=@video.mp4" \
  -F 'metadata={"folder":"intros","public":true}'
```

→ `201`

```json
{ "id": "file_k9m2n5p8q1r4s7t0", "name": "video.mp4",
  "size": 48293120, "mime_type": "video/mp4", "status": "active" }
```

### `GET /v1/files`

Query params: `query` (filename contains), `limit` (1–200, default 50), `cursor`.

```json
{ "files": [ { "id": "file_...", "name": "video.mp4", "project_id": "...",
               "owner_id": "...", "mime_type": "video/mp4", "size": 48293120,
               "status": "active", "metadata": {},
               "created_at": "...", "updated_at": "..." } ],
  "next_cursor": null }
```

Served from an in-memory index — the Telegram channel is not scanned per request.

### `GET /v1/files/{file_id}`

Same `FilePublic` shape as above. Telegram message ids and channel ids are never
included.

### `PATCH /v1/files/{file_id}`

```json
{ "name": "new-name.mp4" }
```

Renames at the application level only. The underlying Telegram media is
untouched — the ZentraGrid filename lives in the METADATA channel.

### `DELETE /v1/files/{file_id}`

```json
{ "id": "file_...", "status": "deleted", "deleted": true }
```

Hard-deletes the blob from the FILES channel, marks metadata `deleted` and
clears the pointer, decrements usage.

### `GET /v1/files/{file_id}/download`

Streamed, chunked. Never buffers the whole file in RAM.

```bash
curl -H "Authorization: Bearer ZTG_live_xxx" \
  https://api.example.com/v1/files/file_abc/download -o video.mp4
```

Headers: `Content-Length`, `Content-Disposition: attachment`, `Accept-Ranges: bytes`.

### `GET /v1/files/{file_id}/stream`

Range-aware, built for `<video>` seeking.

```bash
curl -H "Authorization: Bearer ZTG_live_xxx" \
     -H "Range: bytes=0-1048575" \
     https://api.example.com/v1/files/file_abc/stream
```

```
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 0-1048575/48293120
Content-Length: 1048576
Content-Type: video/mp4
Content-Disposition: inline; filename="video.mp4"
```

Supported: `bytes=start-end`, `bytes=start-`, suffix `bytes=-N`. No `Range`
header → `200` with the full body. A single range response is capped at 16 MiB;
players just request the next one. Unsatisfiable → `416`.

---

## Usage

### `GET /v1/projects/{project_id}/usage`

```json
{ "project_id": "project_x7k2...",
  "total_files": 142, "total_bytes": 8493021184,
  "uploads": 150, "downloads": 1204, "streams": 8821,
  "bandwidth_out_bytes": 91029384756, "api_requests": 10412,
  "quota_bytes": 10737418240, "quota_files": 10000,
  "bytes_remaining": 2244397056, "files_remaining": 9858,
  "updated_at": "..." }
```

---

## Rate limits

Per API key, per operation class. Configurable via env.

| Operation | Env var | Default / min |
|---|---|---|
| Upload | `RATE_LIMIT_UPLOAD_PER_MIN` | 30 |
| Download | `RATE_LIMIT_DOWNLOAD_PER_MIN` | 120 |
| Stream | `RATE_LIMIT_STREAM_PER_MIN` | 240 |
| General | `RATE_LIMIT_GENERAL_PER_MIN` | 300 |
| Dashboard (per Firebase UID) | `RATE_LIMIT_DASHBOARD_PER_MIN` | 120 |

Exceeded → `429` with `Retry-After`. These are starting points, not tuned
production values. Counters are per process — with N Render instances the
effective limit is `limit × N`.

---

## Frontend example

```js
// 1. Google sign-in
const { user } = await signInWithPopup(auth, new GoogleAuthProvider());
const idToken = await user.getIdToken();

// 2. Resolve the owner
const res = await fetch(`${API_BASE}/v1/auth/google`, {
  method: "POST",
  headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({}),
});
const { owner, requires_profile_completion } = await res.json();

if (requires_profile_completion) {
  await fetch(`${API_BASE}/v1/auth/me`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name, company }),
  });
}

// 3. Create a project + key
const project = await (await fetch(`${API_BASE}/v1/projects`, {
  method: "POST",
  headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({ name: "My App" }),
})).json();

const created = await (await fetch(`${API_BASE}/v1/projects/${project.project_id}/keys`, {
  method: "POST",
  headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({ name: "production" }),
})).json();

// Show created.api_key ONCE — it cannot be retrieved again.
```

Video playback needs the key in a header, so use a blob or a proxy route rather
than putting the key in a `<video src>` URL:

```js
const res = await fetch(`${API_BASE}/v1/files/${fileId}/stream`, {
  headers: { Authorization: `Bearer ${apiKey}` },
});
videoEl.src = URL.createObjectURL(await res.blob());
```

For real seeking, proxy `/stream` through your own backend route that injects
the key and forwards the `Range` header — never ship an API key to the browser.
