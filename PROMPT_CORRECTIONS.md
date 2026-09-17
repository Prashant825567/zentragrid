# Corrections to append to your frontend prompt

Your prompt is good — the design direction, structure and rules are all fine.
Paste this block at the **very end** of it, unchanged. It only fixes points
where the prompt disagrees with the real backend. Nothing here touches the
visual design.

---

```
==================================================
BACKEND CORRECTIONS — THESE OVERRIDE ANYTHING ABOVE
==================================================

The following corrections take priority over any conflicting statement
earlier in this prompt. They match the deployed backend exactly.

--------------------------------------------------
1. FIREBASE CONFIG — USE THIS EXACT OBJECT
--------------------------------------------------

The firebaseConfig given earlier has a typo in apiKey and will break
Google sign-in. Use this one, character for character:

const firebaseConfig = {
  apiKey: "AIzaSyBVYRNNyBxtXfLCXFTUFB-XH1ggNl030u4",
  authDomain: "zentragrid.firebaseapp.com",
  projectId: "zentragrid",
  storageBucket: "zentragrid.firebasestorage.app",
  messagingSenderId: "873269002556",
  appId: "1:873269002556:web:9f14acabe4403eb3001e39",
  measurementId: "G-5TYYQRFRZ3"
};

--------------------------------------------------
2. THERE IS NO GLOBAL API KEYS ENDPOINT
--------------------------------------------------

API keys exist ONLY under a project. These are the only key routes:

  POST   /v1/projects/{project_id}/keys
  GET    /v1/projects/{project_id}/keys
  DELETE /v1/projects/{project_id}/keys/{key_id}

There is no GET /v1/keys and no global key list.

So the /dashboard/api-keys page must:
  - first call GET /v1/projects
  - then call GET /v1/projects/{id}/keys for each project
  - merge the results client-side, showing the project name per row
  - run those calls in parallel (Promise.all), not in a loop

Creating a key always requires choosing a project first.

--------------------------------------------------
3. THE BROWSER CANNOT CALL THE FILE ENDPOINTS
--------------------------------------------------

This is the most important correction in this section.

These routes authenticate ONLY with Authorization: Bearer ZTG_live_xxx:

  POST   /v1/files
  GET    /v1/files
  GET    /v1/files/{file_id}
  PATCH  /v1/files/{file_id}
  DELETE /v1/files/{file_id}
  GET    /v1/files/{file_id}/download
  GET    /v1/files/{file_id}/stream

A Firebase ID token is rejected on all of them with 401.

The backend stores only a HASH of every API key. The plaintext is returned
once at creation and is never retrievable again. Therefore the dashboard
cannot hold a usable API key, and these routes cannot be called from browser
code.

Do NOT build /dashboard/storage or /dashboard/storage/[file_id] as pages that
call the backend directly. Do not ask the user to paste their API key into the
browser to make it work — that leaks the secret into DevTools, localStorage and
browser history.

Instead, implement the storage pages through Next.js Route Handlers acting as
a server-side proxy:

  app/api/proxy/files/route.ts              -> POST + GET  /v1/files
  app/api/proxy/files/[file_id]/route.ts    -> GET, PATCH, DELETE
  app/api/proxy/files/[file_id]/download/route.ts
  app/api/proxy/files/[file_id]/stream/route.ts

Each handler must:
  - read the caller's Firebase ID token from the incoming request
  - verify it server-side before doing anything else
  - attach a server-held ZTG_live_ key from process.env (NOT NEXT_PUBLIC_)
  - forward the request to the real backend
  - stream the response body through rather than buffering it
  - forward the Range and Content-Range headers unchanged for /stream
  - never return the API key or echo it in any response

Browser code calls /api/proxy/... only. The ZTG_live_ key never reaches the
client bundle.

If you would rather not build the proxy now, then build the storage pages as
a clearly-labelled documentation/preview state explaining that file operations
run from the customer's own server, and show copy-paste curl/JS/Python
snippets. Do not fake it with mock data presented as real.

--------------------------------------------------
4. GET /v1/files QUERY PARAMETERS
--------------------------------------------------

Only these three are supported:

  query   string, optional, max 120 chars, matches "filename contains"
  limit   integer, 1-200, default 50
  cursor  string, optional, opaque pagination cursor

Response:

  { "files": FilePublic[], "next_cursor": string | null }

There is no sort parameter, no type/MIME filter, no date-range filter.
Sorting and filtering beyond the filename query must be done client-side on
the returned page, and the UI must not imply server-side support that does
not exist. Pagination uses next_cursor, not page numbers.

--------------------------------------------------
5. USAGE IS CUMULATIVE COUNTERS, NOT TIME SERIES
--------------------------------------------------

GET /v1/projects/{project_id}/usage returns exactly these fields:

  project_id, total_files, total_bytes, uploads, downloads, streams,
  bandwidth_out_bytes, api_requests, quota_bytes, quota_files,
  bytes_remaining, files_remaining, updated_at

These are lifetime running totals. There is no per-day breakdown and no
history array, so the backend cannot support 24h / 7d / 30d / 90d filters.

For /dashboard/usage:
  - show the real numbers as stat cards, quota progress bars and simple
    ratio charts (e.g. bytes used vs quota, files used vs quota)
  - do NOT render a time-series line chart from invented data points
  - if you include time-range controls for future use, disable them and
    label them clearly as not yet available

--------------------------------------------------
6. FILEPUBLIC INCLUDES uploaded_by_key_id
--------------------------------------------------

interface FilePublic {
  id: string;
  name: string;
  project_id: string;
  owner_id: string;
  mime_type: string;
  size: number;
  status: string;
  uploaded_by_key_id: string | null;   // which API key uploaded it
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

The file detail page should show which key performed the upload — it is
useful when rotating or investigating a leaked key.

--------------------------------------------------
7. /health/ready RESPONSE SHAPE
--------------------------------------------------

{
  "status": "ready" | "degraded",
  "storage": { "backend": string, "connected": boolean, "authorized": boolean },
  "auth_mode": "admin" | "jwks" | "insecure" | "unconfigured",
  "auth_ready": boolean,
  "firebase_project_id": string | null,
  "service_account_key": boolean
}

Use this for the /status page. Note "storage.backend" is an internal
implementation detail — show a friendly label such as "Storage" and
"Operational" / "Degraded", never the raw backend name.

--------------------------------------------------
8. NO PASSWORD AUTH — GOOGLE ONLY
--------------------------------------------------

The backend supports Google Sign-In only. There are no password, email-link
or password-reset flows, and no backend endpoint exists for them.

  /login             -> a single "Continue with Google" button
  /signup            -> identical to /login; signup happens automatically on
                        first Google sign-in. Either point this route at the
                        same component or redirect it to /login.
  /forgot-password   -> there are no passwords. Either drop this route or
                        make it a short page explaining that ZentraGrid uses
                        Google Sign-In, with a link back to /login.

Do not build email/password forms.

--------------------------------------------------
9. LIMITS THE UI MUST ENFORCE
--------------------------------------------------

  Projects per owner            50
  Active API keys per project   20
  Project name                  120 chars
  Project description           500 chars
  Owner name                    120 chars
  Company                       160 chars
  API key label                 80 chars
  Max upload size               2 GiB (413 PAYLOAD_TOO_LARGE above this)

Show character counters approaching the limit and disable submit past it.
Exceeding the project or key count returns 409 CONFLICT — surface the message.

--------------------------------------------------
10. COMPLETE ERROR CODE LIST
--------------------------------------------------

Every error response is exactly:

  { "error": { "code": string, "message": string } }

400  BAD_REQUEST, VALIDATION_ERROR, INVALID_FILE
401  UNAUTHORIZED, INVALID_ID_TOKEN, INVALID_API_KEY, REVOKED_API_KEY
403  FORBIDDEN, PROFILE_INCOMPLETE
404  NOT_FOUND, FILE_NOT_FOUND, PROJECT_NOT_FOUND, OWNER_NOT_FOUND,
     API_KEY_NOT_FOUND
409  CONFLICT, OWNER_ALREADY_EXISTS
413  PAYLOAD_TOO_LARGE, QUOTA_EXCEEDED
416  RANGE_NOT_SATISFIABLE
429  RATE_LIMITED            (respect the Retry-After header)
500  INTERNAL_ERROR, CONFIGURATION_ERROR
503  STORAGE_UNAVAILABLE

Note: cross-tenant access deliberately returns 404, never 403, so resource
ids cannot be enumerated. Treat a 404 on someone else's resource as normal.

--------------------------------------------------
11. PROJECTS ALREADY EXIST AFTER SIGNUP
--------------------------------------------------

The backend automatically creates a default project when the owner completes
their profile. After PATCH /v1/auth/me, GET /v1/projects returns one project
already.

Do not create a project during onboarding — you would end up with two. The
dashboard should never show a "create your first project" empty state right
after signup.

--------------------------------------------------
12. BILLING HAS NO BACKEND
--------------------------------------------------

There are no billing, invoice, payment-method or plan-change endpoints. The
owner and project objects carry a "plan" string field and nothing more.

Build /dashboard/billing as a read-only page showing the current plan from
owner.plan plus quota usage from the usage endpoint. Label anything else as
coming soon. Do not build invoice tables or payment forms filled with fake
data.

--------------------------------------------------
13. NEVER MENTION THE STORAGE IMPLEMENTATION
--------------------------------------------------

The backend persists data in private Telegram channels. This is an internal
detail. The API already strips every channel id and message id.

Never surface the words Telegram, channel, or message id anywhere in the UI,
docs, code comments or status page. To the user this is simply "ZentraGrid
storage".

--------------------------------------------------
14. ENVIRONMENT VARIABLES
--------------------------------------------------

  NEXT_PUBLIC_API_BASE_URL   the backend base URL, e.g.
                             http://localhost:8000 during development
  ZENTRAGRID_API_KEY         server-only ZTG_live_ key for the proxy routes.
                             MUST NOT be prefixed NEXT_PUBLIC_.

Never place a ZTG_live_ key, a Firebase private key, or any Telegram value in
a NEXT_PUBLIC_ variable or anywhere in client code.
```

---

## Why each correction matters

**1 — Firebase apiKey typo.** Your prompt has
`...NyBxtXlcXFTUFB...`, the real key is `...NyBxtXfLCXFTUFB...` (one character
different, and one character shorter). Google sign-in would fail with
`auth/api-key-not-valid` on every attempt and it would look like a code bug.

**2 — `/dashboard/api-keys`.** Keys only exist under a project; there is no
global list endpoint. Without this the AI invents `GET /v1/keys` and the page
404s.

**3 — The storage pages.** This is the significant one. The dashboard
physically cannot call the file endpoints: they need a `ZTG_live_` key, and the
backend only ever stores a hash of it. Anything the AI builds here without
guidance will either be mock data pretending to be real, or a form asking the
user to paste their secret key into the browser. The proxy route pattern is the
correct fix.

**4, 5 — Search and usage filters.** Your prompt asks for sorting, filtering
and 24h/7d/30d/90d charts. The backend supports a filename `query` and
cumulative counters only. Left unsaid, the AI generates fake time-series data
that looks real.

**8 — `/signup` and `/forgot-password`.** Google-only auth means there is no
password to reset. These routes would otherwise get email/password forms wired
to endpoints that do not exist.

**11 — Default project.** The backend creates one at signup; onboarding that
also creates one produces two projects for every new user.

Everything else in your prompt — the liquid glass system, the colours, the 3D
hero, the page list, Anime.js, the copy — is untouched.
