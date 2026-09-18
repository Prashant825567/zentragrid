# ZentraGrid — saare routes aur unka kaam

Total 21 routes. Teen groups: public, dashboard (Firebase token), developer (API key).

---

## Pehla sawaal: pehli baar vs dusri baar login

Haan bhai, ye **bana hua hai aur chal raha hai**. Sab kuch ek hi route pe hota hai:
`POST /v1/auth/google`.

### Kaise pehchanta hai

Backend **email** se dhundta hai (email nahi mila toh Firebase UID se). Email hi
asli pehchan hai kyunki wo kabhi badalti nahi.

```
Token aaya
   │
   ├── email OWNERS channel me hai?
   │
   ├── NAHI  → naya owner banao
   │           is_new_owner = true
   │           requires_profile_completion = true
   │           → frontend Name + Company ka form dikhaye
   │
   └── HAAN  → purana owner load karo
               is_new_owner = false
               requires_profile_completion = false
               name aur company purane hi bhejo
               → frontend seedha dashboard khole
```

### Live test ka output

```
PEHLI BAAR login (naya email)
   is_new_owner                : True
   requires_profile_completion : True    <- form dikhao
   owner.company               : None
   owner_id                    : owner_k5gexzujc7qq1mm6

PATCH /v1/auth/me  (user ne form bhara)
   profile_completed           : True
   default project bana        : ZentraGrid

DUSRI BAAR login (wahi email, 3 baar)
   login #1: is_new=False  needs_form=False  name='Prashant Rajput'  same_id=True
   login #2: is_new=False  needs_form=False  name='Prashant Rajput'  same_id=True
   login #3: is_new=False  needs_form=False  name='Prashant Rajput'  same_id=True

Google ka naam badal gaya toh?
   backend me naam : 'Prashant Rajput'   <- purana hi raha, Google wala ignore
   owner_id wahi   : True                 (koi duplicate nahi)
```

Teen baar login kiya — teeno baar wahi `owner_id`, wahi naam, form dobara nahi
maanga. Aur agar user ne apna Google profile ka naam badal bhi diya, backend
**purana stored naam hi rakhta hai**. Ye jaan-boojh kar hai: tumhare records me
jo naam hai wahi sach hai.

### Frontend ko bas itna karna hai

```ts
const res = await fetch(`${API}/v1/auth/google`, {
  method: "POST",
  headers: { Authorization: `Bearer ${idToken}` },
  body: "{}"
});
const { owner, is_new_owner, requires_profile_completion } = await res.json();

if (requires_profile_completion) {
  // Name + Company form dikhao → PATCH /v1/auth/me
} else {
  // seedha dashboard, owner.name aur owner.company use karo
}
```

---

# GROUP 1 — Public (koi auth nahi)

### `GET /`
Service ki basic info. Health check ke liye.

### `GET /health`
Zinda hai ya nahi. **Render isi ko ping karta hai.**

```json
{ "status": "ok", "service": "ZentraGrid", "env": "production", "storage_backend": "telegram" }
```

### `GET /health/ready`
Sab dependencies judi hain ya nahi. `/status` page ke liye.

```json
{
  "status": "ready",
  "storage": { "backend": "telegram", "connected": true, "authorized": true },
  "auth_mode": "jwks",
  "auth_ready": true,
  "firebase_project_id": "zentragrid",
  "service_account_key": false
}
```

`connected: false` → storage down. `auth_mode: unconfigured` → `FIREBASE_PROJECT_ID` missing.

---

# GROUP 2 — Dashboard

Header: `Authorization: Bearer <FIREBASE_ID_TOKEN>`

## Auth

### `POST /v1/auth/google`
**Login aur signup dono.** Upar wala pura logic isi me hai.

Body: `{}`

```json
{
  "owner": { "owner_id": "...", "email": "...", "name": "...", "company": "...",
             "picture": "...", "plan": "free", "profile_completed": true,
             "created_at": "...", "updated_at": "..." },
  "is_new_owner": false,
  "requires_profile_completion": false
}
```

### `GET /v1/auth/me`
Abhi ka owner profile. Page reload pe ise call karo.

### `PATCH /v1/auth/me`
Naam aur company save karna. Pehli baar signup me, ya settings se edit.

```json
{ "name": "Prashant", "company": "ZentraGrid" }
```

**Important:** ye call hote hi backend **apne aap ek default project bana deta
hai** (company ke naam se). Frontend ko project banane ki zaroorat nahi.

## Projects

### `POST /v1/projects`
Naya project. Body: `{ "name": "...", "description": "..." }` → `201`

Limit 50 per owner. Same naam dobara → `409 CONFLICT`.

### `GET /v1/projects`
Saare projects. → `{ "projects": [...] }`

### `GET /v1/projects/{project_id}`
Ek project ki detail.

### `DELETE /v1/projects/{project_id}`
Project delete + **uski saari keys ek saath revoke**. → `204`

Confirm modal me ye baat likhna zaroori hai.

## API Keys

### `POST /v1/projects/{project_id}/keys`
Nayi key banao. Body: `{ "name": "production" }` → `201`

```json
{
  "key": { "key_id": "key_...", "key_hint": "f4c1", "revoked": false, ... },
  "api_key": "ZTG_live_xY9kL2mNpQ7rS4tU8vW1xZ3aB6cD0eF5gH"
}
```

**`api_key` sirf abhi milta hai, dobara kabhi nahi.** Backend uska hash rakhta
hai. Modal me copy button ke saath dikhao, aur modal backdrop click pe band na
ho — user galti se close kar dega toh key hamesha ke liye gayi.

Limit 20 active keys per project.

### `GET /v1/projects/{project_id}/keys`
Keys ki list. Sirf `key_hint` (last 4 chars) aata hai, plaintext nahi.

### `DELETE /v1/projects/{project_id}/keys/{key_id}`
Key revoke. Turant band ho jaati hai.

> **Koi global keys endpoint nahi hai.** `/v1/keys` exist nahi karta.
> `/dashboard/api-keys` page banane ke liye: pehle `GET /v1/projects`, phir
> har project ki keys parallel me, phir merge.

## Usage

### `GET /v1/projects/{project_id}/usage`

```json
{
  "project_id": "...",
  "total_files": 142, "total_bytes": 8493021184,
  "uploads": 150, "downloads": 1204, "streams": 8821,
  "bandwidth_out_bytes": 91029384756, "api_requests": 10412,
  "quota_bytes": 10737418240, "quota_files": 10000,
  "bytes_remaining": 2244397056, "files_remaining": 9858,
  "updated_at": "..."
}
```

Ye **lifetime cumulative counters** hain. Din-wise history nahi hai, isliye
24h/7d/30d wale charts possible nahi.

---

# GROUP 3 — Developer API

Header: `Authorization: Bearer ZTG_live_xxx`

Firebase token yahan **nahi** chalega — `401` milega.

> **Browser se ye call nahi kar sakte.** Key ka sirf hash store hota hai, toh
> dashboard ke paas key hoti hi nahi. Next.js route handler proxy banao, key
> server pe `process.env.ZENTRAGRID_API_KEY` me rakho.

### `POST /v1/files`
Upload. `multipart/form-data`

| Field | Zaroori | Kaam |
|---|---|---|
| `file` | haan | binary |
| `filename` | nahi | naam override |
| `metadata` | nahi | JSON, max 32 flat keys |

```json
{ "id": "file_abc123", "name": "video.mp4", "size": 48293120,
  "mime_type": "video/mp4", "status": "active" }
```

Max 2 GiB. Upar gaya toh `413`.

### `GET /v1/files`
List + search. Params: `query` (filename contains, max 120), `limit` (1-200,
default 50), `cursor`.

```json
{ "files": [...], "next_cursor": null }
```

Sort/filter/date-range params nahi hain — wo client-side karna padega.

### `GET /v1/files/{file_id}`
Metadata.

```json
{ "id": "...", "name": "...", "project_id": "...", "owner_id": "...",
  "mime_type": "...", "size": 207493, "status": "active",
  "uploaded_by_key_id": "key_...", "metadata": {},
  "created_at": "...", "updated_at": "..." }
```

`uploaded_by_key_id` batata hai **kis key se upload hua tha** — key leak hone
pe kaam aata hai.

### `PATCH /v1/files/{file_id}`
Rename. Body: `{ "name": "new-name.mp4" }`

Sirf ZentraGrid ka metadata badalta hai, asli file waisi rehti hai.

### `DELETE /v1/files/{file_id}`
File delete. Blob hat jaata hai, metadata `deleted` ho jaata hai, usage kam.

### `GET /v1/files/{file_id}/download`
Streamed download. Poori file RAM me kabhi nahi aati.

### `GET /v1/files/{file_id}/stream`
Video streaming, Range support.

```
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 0-1048575/48293120
Content-Length: 1048576
```

`bytes=start-end`, `bytes=start-`, `bytes=-N` teeno chalte hain. Ek response
max 16 MiB — player agla range maang lega. Galat range → `416`.

---

# Poora flow

```
Founder Google se login          POST /v1/auth/google
   │                             → is_new_owner: true
   ▼
Name + Company bhara             PATCH /v1/auth/me
   │                             → default project auto-bana
   ▼
Key generate ki                  POST /v1/projects/{id}/keys
   │                             → ZTG_live_... (ek hi baar)
   ▼
Apne app me daali                ZENTRAGRID_API_KEY=ZTG_live_...
   │
   ▼
App ne file upload ki            POST /v1/files
   │                             → Bearer ZTG_live_...
   ▼
App ne users ko serve ki         GET /v1/files/{id}/stream
```

---

# Error format

Har error bilkul ye shape me:

```json
{ "error": { "code": "INVALID_API_KEY", "message": "..." } }
```

| HTTP | Codes |
|---|---|
| 400 | `BAD_REQUEST`, `VALIDATION_ERROR`, `INVALID_FILE` |
| 401 | `UNAUTHORIZED`, `INVALID_ID_TOKEN`, `INVALID_API_KEY`, `REVOKED_API_KEY` |
| 403 | `FORBIDDEN`, `PROFILE_INCOMPLETE` |
| 404 | `NOT_FOUND`, `FILE_NOT_FOUND`, `PROJECT_NOT_FOUND`, `OWNER_NOT_FOUND`, `API_KEY_NOT_FOUND` |
| 409 | `CONFLICT`, `OWNER_ALREADY_EXISTS` |
| 413 | `PAYLOAD_TOO_LARGE`, `QUOTA_EXCEEDED` |
| 416 | `RANGE_NOT_SATISFIABLE` |
| 429 | `RATE_LIMITED` (+ `Retry-After` header) |
| 500 | `INTERNAL_ERROR`, `CONFIGURATION_ERROR` |
| 503 | `STORAGE_UNAVAILABLE` |

Dusre owner ki cheez maangi toh `404` aata hai, `403` nahi — taaki koi IDs
guess karke doosron ka data na dhoondh sake.

---

# Limits

| Cheez | Limit |
|---|---|
| Projects per owner | 50 |
| Active keys per project | 20 |
| Project name | 120 chars |
| Project description | 500 chars |
| Owner name | 120 chars |
| Company | 160 chars |
| Key label | 80 chars |
| Upload size | 2 GiB |

# Rate limits (env se configurable)

| Kaam | Default /min |
|---|---|
| Upload | 30 |
| Download | 120 |
| Stream | 240 |
| General | 300 |
| Dashboard | 120 |
