# ZentraGrid

**Developer storage infrastructure API for startups.**

Upload, download, stream, rename and delete files through a clean REST API.
Owners sign in with Google (Firebase Auth), issue API keys per project, and
their developers use those keys against the file endpoints.

There is **no SQL/NoSQL application database**. All persistence lives in three
private Telegram channels behind repository abstractions, so the storage layer
can be swapped later without touching business logic.

---

## 1. Architecture

```
Browser (dashboard)
   │  Continue with Google
   ▼
Firebase Authentication ──► Firebase ID token
   │
   ▼  Authorization: Bearer <FIREBASE_ID_TOKEN>
ZentraGrid API (FastAPI on Render)
   │  Firebase Admin verifies token → owner lookup
   │
   ├── Owners / Projects / API keys / Usage
   └── Files
        ▲
        │  Authorization: Bearer ZTG_live_...
   Developer's application
```

Internally:

```
app/main.py                 application factory, CORS, middleware, lifespan
│
├── core/
│   ├── config.py           env-driven settings (pydantic-settings)
│   ├── security.py         auth dependencies, ownership derivation
│   ├── errors.py           ZentraGridError hierarchy + JSON envelope
│   ├── storage.py          composition root: builds repositories
│   ├── ratelimit.py        sliding-window limiter
│   └── logging.py          request context + secret redaction
│
├── auth/firebase.py        Firebase Admin init + ID-token verification
│
├── telegram/               ◄── the ONLY place Telethon is imported
│   ├── client.py           MTProto singleton, entity resolution
│   ├── messages.py         RecordChannel / MediaChannel contracts
│   ├── records.py          JSON records as Telegram messages
│   ├── files.py            blob upload / ranged download / delete
│   ├── owners.py           OWNERS channel binding
│   ├── metadata.py         METADATA channel binding
│   └── memory.py           in-memory backend (tests / local dev)
│
├── repositories/           owners, projects, api_keys, files, usage
├── services/               owner, project, api_key, file, streaming, usage
├── api/routes/             auth, projects, keys, files, usage, health
├── models/                 pydantic domain + API models
└── utils/                  ids, hashing, validators
```

**The replaceability rule:** services depend on repositories, repositories
depend on the abstract `RecordChannel` / `MediaChannel` contracts in
`telegram/messages.py`. To move to S3 + Postgres later, implement those two
interfaces and change `_build_channels()` in `core/storage.py`. Nothing else
changes.

### Indexing (why Telegram isn't scanned per request)

Each repository loads its records **once** at startup and keeps an in-process
index (`email → owner`, `key_hash → key`, `project → files`). Writes update
both Telegram and the index. So a file lookup is a dict hit, not a channel
scan. `UsageRepository` additionally batches counter writes (dirty set +
threshold flush) so a download doesn't cost a message edit.

---

## 2. The three Telegram channels

All three must be **private** channels the session account belongs to.

| Channel | Env var | Contents |
|---|---|---|
| **FILES** | `TG_FILES_CHANNEL` | Raw uploaded blobs (images, video, PDFs, assets) |
| **METADATA** | `TG_METADATA_CHANNEL` | One JSON record per file, pointing at the FILES message id |
| **OWNERS** | `TG_OWNERS_CHANNEL` | Owner records, projects, API-key metadata, plans, quotas, usage |

Raw media is never mixed with owner metadata.

**Deletion semantics differ per channel** — worth knowing when you inspect them:

| Action | FILES | METADATA | OWNERS |
|---|---|---|---|
| `DELETE /v1/files/{id}` | message **hard-deleted** (blob gone) | record marked `status: "deleted"`, pointer cleared — message stays | usage counters decremented |
| `DELETE /v1/projects/{id}` | untouched | untouched | project marked `deleted`, keys marked `revoked` — messages stay |

So an empty FILES channel after a delete is correct behaviour, while OWNERS and
METADATA keep their messages as an audit trail.

Uploads carry a real `DocumentAttributeFilename` and the detected MIME type, so
files appear in Telegram with their proper name (`video.mp4`, `photo.jpg`)
rather than a temp-file name. Videos are sent with `supports_streaming`.

Records are stored as plain-text messages prefixed with a marker so they're
greppable inside Telegram itself:

```
#zg_record #file
{"created_at":"2026-09-16T00:00:00Z","file_id":"file_abc123", ...}
```

Example records:

```jsonc
// OWNERS channel
{"record_type":"owner","owner_id":"owner_001","firebase_uid":"…",
 "email":"owner@example.com","name":"Rahul","company":"Example Startup",
 "profile_completed":true,"created_at":"…","updated_at":"…"}

{"record_type":"api_key","key_id":"key_001","owner_id":"owner_001",
 "project_id":"project_001","key_hash":"<hmac-sha256>","key_hint":"f4c1",
 "revoked":false,"created_at":"…"}

// METADATA channel
{"record_type":"file","file_id":"file_abc123","owner_id":"owner_001",
 "project_id":"project_001","telegram_message_id":12345,
 "filename":"video.mp4","mime_type":"video/mp4","size":48293120,
 "status":"active","created_at":"…"}
```

---

## 3. Environment variables

Copy `.env.example` → `.env`. **Never commit `.env`.**

| Variable | Required | Notes |
|---|---|---|
| `APP_ENV` | yes | `development` / `staging` / `production` / `test` |
| `CORS_ORIGINS` | yes | Comma-separated. Wildcard rejected in production |
| `STORAGE_BACKEND` | yes | `telegram` (real) or `memory` (dev/tests) |
| `TG_API_ID` | yes | From my.telegram.org |
| `TG_API_HASH` | yes | **Secret** |
| `TG_SESSION` | yes | **Secret** — Telethon StringSession |
| `TG_FILES_CHANNEL` | yes | e.g. `-100ZZZZZZZZZZ` |
| `TG_METADATA_CHANNEL` | yes | |
| `TG_OWNERS_CHANNEL` | yes | |
| `FIREBASE_PROJECT_ID` | yes | `zentragrid`. Alone this enables keyless (`jwks`) verification |
| `FIREBASE_CLIENT_EMAIL` | no | Only for full Admin SDK mode |
| `FIREBASE_PRIVATE_KEY` | no | **Secret** — only for Admin SDK mode. `\n` handled automatically |
| `API_KEY_PEPPER` | yes | **Secret** — rotating it invalidates every API key |
| `MAX_UPLOAD_BYTES` | no | Default 2 GiB |
| `RATE_LIMIT_*_PER_MIN` | no | See §10 |
| `AUTH_ALLOW_INSECURE_TOKENS` | no | Dev only. Boot fails if `true` in production |

---

## 4. Firebase setup

1. Firebase console → your `zentragrid` project.
2. **Authentication → Sign-in method → Google → Enable.**
3. **Authentication → Settings → Authorized domains:** add your frontend
   domain (and `localhost` for dev).
4. Set `FIREBASE_PROJECT_ID=zentragrid`. **That is all that is required.**

### Two verification modes

ZentraGrid only ever *verifies* ID tokens — it never mints custom tokens or
manages users. That needs Google's **public** signing keys, not a private one.

| Mode | Requires | When |
|---|---|---|
| `jwks` | `FIREBASE_PROJECT_ID` | Default. Keyless verification against Google's published keys |
| `admin` | + `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY` | Optional. Needed only for custom tokens / user management / mid-life revocation checks |

Both verify signature, issuer, audience and expiry. `jwks` mode is the right
choice if your Google Cloud org policy
(`iam.disableServiceAccountKeyCreation`) blocks key downloads — a common
default on newer projects.

To use `admin` mode: **Project settings → Service accounts → Generate new
private key**, then take `client_email` and `private_key` from the JSON. The
private key contains real newlines; literal `\n` escapes are un-escaped
automatically by `config.py`.

---

## 5. Google Sign-In (frontend side)

The web config is **client-side and public** — it is not a server credential:

```js
const firebaseConfig = {
  apiKey: "AIzaSyBVYRNNyBxtXfLCXFTUFB-XH1ggNl030u4",
  authDomain: "zentragrid.firebaseapp.com",
  projectId: "zentragrid",
  storageBucket: "zentragrid.firebasestorage.app",
  messagingSenderId: "873269002556",
  appId: "1:873269002556:web:9f14acabe4403eb3001e39",
  measurementId: "G-5TYYQRFRZ3"
};
```

```js
import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";

const auth = getAuth(initializeApp(firebaseConfig));

async function continueWithGoogle() {
  const { user } = await signInWithPopup(auth, new GoogleAuthProvider());
  const idToken = await user.getIdToken();

  const res = await fetch(`${API_BASE}/v1/auth/google`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const data = await res.json();

  if (data.requires_profile_completion) {
    // First-time owner → show the Name + Company form, then:
    // PATCH /v1/auth/me { name, company }
  } else {
    // Returning owner → go straight to the dashboard with data.owner
  }
}
```

The browser **never** talks to Telegram. Firebase Admin credentials **never**
go to the frontend.

---

## 6. Telegram API setup

1. Go to <https://my.telegram.org> → **API development tools**.
2. Create an application → note **api_id** and **api_hash**.
3. Put them in `TG_API_ID` / `TG_API_HASH`.

---

## 7. String session

Generate once, on your own machine — never on Render:

```bash
export TG_API_ID=... TG_API_HASH=...
python scripts/generate_session.py
```

You'll be prompted for phone number, login code and 2FA password. The printed
string goes into `TG_SESSION`.

> The session string is a **full credential for your Telegram account**. Treat
> it like a password: secret env var only, never committed, never logged, never
> returned by any endpoint. If it leaks, revoke it in Telegram →
> *Settings → Devices → Terminate session*, then regenerate.

---

## 8. Private channel setup

1. In Telegram, create **three private channels**: `FILES`, `METADATA`,
   `OWNERS` (Channel type must be *Private* — no public username).
2. The account whose session you generated must be a **member with admin
   rights** (post, edit and delete messages) in all three.
3. Get the ids:

```bash
python scripts/list_channels.py
```

Copy the ids including the leading `-100` into the three env vars.

> Delete permission matters: `DELETE /v1/files/{id}` removes the underlying
> Telegram message.

---

## 9. Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # fill in your values

uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> (disabled in production).

**Without any credentials** — run entirely in memory with fake tokens:

```bash
STORAGE_BACKEND=memory AUTH_ALLOW_INSECURE_TOKENS=true uvicorn app.main:app --reload
```

### Tests

```bash
pytest -q          # 86 tests, no Telegram/Firebase credentials needed
```

### Real end-to-end check against your Telegram channels

```bash
python scripts/e2e_real_test.py
```

Runs the full flow — owner signup, returning login, project, API key, photo
upload, metadata, download with SHA-256 verification, Range streaming, rename,
isolation, revocation, delete — against live Telegram.

> **This script cleans up after itself.** Its last step deletes the uploaded
> file, which removes the message from the FILES channel. So after a run the
> FILES channel looks empty — that is the delete test passing, not a bug.
> OWNERS and METADATA records remain, because those are *soft*-deleted
> (`status: "deleted"`) and the message is intentionally kept as an audit trail.

To upload files and **keep** them so you can see them in Telegram:

```bash
python scripts/demo_keep.py
```

---

## 10. Render deployment

1. Push the repo to GitHub.
2. Render → **New → Blueprint** → select the repo (`render.yaml` is detected).
3. Fill in the secret env vars marked `sync: false` in the dashboard:
   `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`, the three channel ids,
   `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY`.
   `API_KEY_PEPPER` is auto-generated.
4. Set `CORS_ORIGINS` to your real frontend domain(s).
5. Deploy. Health check: `/health`.

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Operational notes**

- Use a paid instance. Free instances sleep, which drops the MTProto
  connection and makes cold starts slow.
- Keep `--workers 1`. Each worker holds its own MTProto session and its own
  in-memory index; multiple workers multiply Telegram connections and make the
  rate limiter per-worker. Scale with Render instances + a shared cache later.
- Rate limits are per process — with N instances the effective limit is
  `limit × N` until Redis-backed limiting is added.

---

## 11. API usage

Base URL: `https://<your-service>.onrender.com`

### Errors

Every error uses the same envelope:

```json
{ "error": { "code": "INVALID_API_KEY", "message": "The provided API key is invalid." } }
```

Status codes: `400` `401` `403` `404` `409` `413` `416` `429` `500`.

Common codes: `INVALID_ID_TOKEN`, `INVALID_API_KEY`, `REVOKED_API_KEY`,
`PROFILE_INCOMPLETE`, `FILE_NOT_FOUND`, `PROJECT_NOT_FOUND`, `VALIDATION_ERROR`,
`INVALID_FILE`, `PAYLOAD_TOO_LARGE`, `QUOTA_EXCEEDED`, `RANGE_NOT_SATISFIABLE`,
`RATE_LIMITED`.

### Dashboard endpoints — `Authorization: Bearer <FIREBASE_ID_TOKEN>`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/auth/google` | Sign in / sign up |
| `GET` | `/v1/auth/me` | Current owner profile |
| `PATCH` | `/v1/auth/me` | Complete profile (name, company) |
| `POST` | `/v1/projects` | Create project |
| `GET` | `/v1/projects` | List projects |
| `GET` | `/v1/projects/{id}` | Get project |
| `DELETE` | `/v1/projects/{id}` | Delete project + revoke its keys |
| `POST` | `/v1/projects/{id}/keys` | Create API key |
| `GET` | `/v1/projects/{id}/keys` | List keys (no plaintext) |
| `DELETE` | `/v1/projects/{id}/keys/{key_id}` | Revoke key |
| `GET` | `/v1/projects/{id}/usage` | Usage + quota |

**Owner login behaviour**

```
FIRST LOGIN   email absent in OWNERS  → create record
                                      → is_new_owner: true
                                      → requires_profile_completion: true
                                      → ask Name + Company → PATCH /v1/auth/me

SECOND LOGIN  email present           → is_new_owner: false
                                      → requires_profile_completion: false
                                      → stored name/company returned
                                      → straight to dashboard
```

Identity matches on normalised email first, then Firebase UID. Repeated logins
never create a duplicate record, and a returning owner's stored profile always
wins over whatever Google reports.

### Developer endpoints — `Authorization: Bearer ZTG_live_...`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/files` | Upload (multipart) |
| `GET` | `/v1/files` | List / simple filename lookup |
| `GET` | `/v1/files/{id}` | Metadata |
| `PATCH` | `/v1/files/{id}` | Rename |
| `DELETE` | `/v1/files/{id}` | Delete |
| `GET` | `/v1/files/{id}/download` | Streamed download |
| `GET` | `/v1/files/{id}/stream` | Range-aware streaming |
| `GET` | `/health` | Liveness |

**Upload**

```bash
curl -X POST https://api.zentragrid.app/v1/files \
  -H "Authorization: Bearer ZTG_live_xxx" \
  -F "file=@video.mp4" \
  -F 'metadata={"folder":"intros"}'
```

```json
{ "id": "file_abc123", "name": "video.mp4", "size": 48293120,
  "mime_type": "video/mp4", "status": "active" }
```

Form fields: `file` (required), `filename` (optional override), `metadata`
(optional JSON object, ≤32 flat keys).

**Download** — streamed, never buffered whole in RAM.

```bash
curl -L -H "Authorization: Bearer ZTG_live_xxx" \
  https://api.zentragrid.app/v1/files/file_abc123/download -o video.mp4
```

**Streaming with Range** — built for `<video>` seeking.

```bash
curl -H "Authorization: Bearer ZTG_live_xxx" \
     -H "Range: bytes=0-1048575" \
     https://api.zentragrid.app/v1/files/file_abc123/stream
```

```
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 0-1048575/48293120
Content-Length: 1048576
Content-Type: video/mp4
```

Supports `bytes=start-end`, `bytes=start-` and suffix `bytes=-N`. A single
range response is capped at 16 MiB; players simply request the next range.
Unsatisfiable ranges return `416`.

**Rename** — application-level only; the underlying Telegram media is not
renamed, the ZentraGrid filename lives in METADATA.

```bash
curl -X PATCH https://api.zentragrid.app/v1/files/file_abc123 \
  -H "Authorization: Bearer ZTG_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"name":"new-name.mp4"}'
```

### API keys

Format `ZTG_live_<43 url-safe chars>`. The plaintext is returned **once**, by
`POST /v1/projects/{id}/keys`, and is never recoverable afterwards — only an
HMAC-SHA256 digest and a 4-character hint are stored.

```json
{ "key": { "key_id": "key_001", "key_hint": "f4c1", "revoked": false, ... },
  "api_key": "ZTG_live_…"  }
```

### Search

MVP is a simple indexed filename lookup: `GET /v1/files?query=video`. It reads
the in-memory index, never scanning the storage channel. The repository
abstraction is where a real search index or cache plugs in later.

---

## 12. Security considerations

- **Firebase ID tokens** are verified server-side with the Admin SDK. The
  frontend web API key is never used as a server credential.
- **API keys** are HMAC-SHA256 hashed with a server-side pepper. Plaintext is
  never stored. Lookups are constant-time comparisons on the digest.
- **Ownership is always derived** from the verified token or API key. A
  client-supplied `owner_id` / `project_id` is ignored — there's a test for it.
- **Project isolation:** cross-project access returns `404`, not `403`, so ids
  aren't enumerable.
- **Input validation:** filenames are sanitised against path traversal and
  control characters, extensions can be blocklisted, MIME types allowlisted,
  metadata capped at 32 flat JSON-safe keys.
- **Request size limits:** uploads spool to a temp file and abort the moment
  `MAX_UPLOAD_BYTES` is exceeded; quota is checked before and after spooling.
- **Rate limiting** per API key, per operation class (upload / download /
  stream / general) and per Firebase UID for dashboard routes. `429` responses
  carry `Retry-After`.
- **CORS** is an explicit allowlist; the app refuses to boot with `*` in
  production.
- **Security headers:** `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store`, plus HSTS
  in production.
- **Logging** records request id, method, path, status, duration, project id
  and file id. A redaction filter scrubs the session string, API hash, private
  key, pepper and any `ZTG_live_…` pattern before anything reaches stdout.
  Telethon's logger is pinned to `WARNING`.
- **Telegram internals are never exposed:** `telegram_message_id` and channel
  ids are stripped from every API response, and there is no endpoint that can
  return `TG_SESSION`.
- **Production boot guards:** the app refuses to start if
  `AUTH_ALLOW_INSECURE_TOKENS` is on, `API_KEY_PEPPER` is still the default, or
  CORS is wildcarded. `/docs`, `/redoc` and `/openapi.json` are disabled.

### Known limitations

- Rate limiter and indexes are per process — see the Render notes above.
- Telegram enforces its own flood limits; sustained heavy upload traffic will
  hit `FloodWaitError` on the account. Add a queue/retry layer before scaling.
- Files above Telegram's per-file ceiling (2 GB, 4 GB with Premium) need
  client-side chunking into multiple parts.

---

## 13. Verified end-to-end

`scripts/e2e_real_test.py` was run against live Telegram channels —
**46/46 checks passed**, including a 207 KB JPEG uploaded, downloaded and
verified byte-identical by SHA-256, plus mid-file Range seeks returning exact
byte slices.
