# Prompt for Google AI Studio — ZentraGrid Dashboard Frontend

Copy everything between the lines below into AI Studio.

---

You are updating the frontend for **ZentraGrid**, a developer storage
infrastructure product. The backend is already built, deployed and working —
do not redesign it, do not invent endpoints, do not change the contract.

## What the product is

ZentraGrid gives startups storage for their apps' user content. A founder who
built an Instagram-like app needs somewhere to put their users' photos and
videos. They sign in to ZentraGrid with Google, get an API key, drop that key
into their own backend, and their app uploads through the ZentraGrid API.

There is **one type of user: the owner** (the founder). The dashboard you are
building is for them.

## CRITICAL: where Google Sign-In happens

**Google Sign-In runs in the FRONTEND. The backend only verifies the result.**

This is the single most important thing to get right.

```
BROWSER (your code)                          BACKEND (already built)
─────────────────────                        ───────────────────────
1. User clicks "Continue with Google"
2. Firebase opens the Google popup
3. User picks their account
4. Firebase returns a User object
5. await user.getIdToken()  ──────────────►
   sends it as:                             6. Verifies the token's signature
   Authorization: Bearer <idToken>             against Google's public keys
                                            7. Looks up / creates the owner
                                   ◄─────── 8. Returns the owner record
```

Concretely:

- The **Firebase Web SDK lives only in the browser.** You install
  `firebase`, call `initializeApp`, `getAuth`, `signInWithPopup`.
- The **backend never shows a Google login screen.** There is no
  `/login` redirect, no OAuth callback URL, no `code` exchange to implement.
  Do not build one.
- The browser **never talks to Telegram** and never sees Telegram credentials.
- The backend has no session cookies. Every request carries a fresh Firebase
  ID token in the `Authorization` header.

### Firebase web config (public, safe to ship in frontend code)

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

This `apiKey` is a public client identifier, not a secret. It is safe in
frontend code. Do **not** put any service-account key or private key in the
frontend — the backend handles all of that.

### Token handling rules

- Get the token with `await user.getIdToken()` **before every API call**.
  Firebase caches it and refreshes automatically when it is close to expiring,
  so calling it every time is correct and cheap.
- Tokens expire after 1 hour. Never cache one in `localStorage` yourself.
- Use `onAuthStateChanged` to restore the session on page reload. Show a
  loading state until it fires — do not flash the login page at a signed-in
  user.
- On `401` from the backend: force-refresh once with `getIdToken(true)` and
  retry. If it fails again, sign out and send them to the login page.

---

## The exact sign-in flow to implement

### First-time user

1. User clicks **"Continue with Google"** → `signInWithPopup`.
2. Get the ID token, then `POST /v1/auth/google` with an empty JSON body `{}`.
3. Response comes back with `requires_profile_completion: true` and
   `is_new_owner: true`.
4. **Show a profile form asking for Name and Company.** Do not skip this —
   the rest of the dashboard is blocked until it is filled.
5. Submit with `PATCH /v1/auth/me` → `{ "name": "...", "company": "..." }`.
6. Now go to the dashboard. A default project has been created automatically
   by the backend at this point — you do not need to create one.

### Returning user

1. Same click, same `POST /v1/auth/google`.
2. Response has `is_new_owner: false` and `requires_profile_completion: false`,
   plus the stored `name` and `company`.
3. **Go straight to the dashboard. Never ask for their name again.**
   Use the `name` and `company` from the response — do not use the Google
   display name, the stored profile always wins.

Signing in repeatedly never creates a duplicate account. The backend matches on
email first, then Firebase UID.

---

## Backend API contract

Base URL comes from an env var, e.g. `VITE_API_BASE` /
`NEXT_PUBLIC_API_BASE`. Never hardcode it.

All dashboard endpoints require:

```
Authorization: Bearer <FIREBASE_ID_TOKEN>
```

### Errors — every failure has this exact shape

```json
{ "error": { "code": "PROFILE_INCOMPLETE", "message": "Owner profile must be completed..." } }
```

Write one `apiFetch` helper that attaches the token, parses this envelope, and
throws a typed error. Handle these codes specifically:

| Code | HTTP | What the UI should do |
|---|---|---|
| `INVALID_ID_TOKEN` | 401 | Refresh token once, then sign out |
| `PROFILE_INCOMPLETE` | 403 | Redirect to the profile form |
| `PROJECT_NOT_FOUND` | 404 | Show "project not found", go back to list |
| `CONFLICT` | 409 | Show the message inline (e.g. duplicate project name) |
| `RATE_LIMITED` | 429 | Show "too many requests", respect `Retry-After` |
| `QUOTA_EXCEEDED` | 413 | Show an upgrade / free-up-space prompt |

### Endpoints

**Auth**

```
POST /v1/auth/google      body: {}  (or {name, company} on first signup)
  → { owner: OwnerPublic, is_new_owner: bool, requires_profile_completion: bool }

GET /v1/auth/me           → OwnerPublic
PATCH /v1/auth/me         body: { name: string, company?: string } → OwnerPublic
```

`OwnerPublic`:
```ts
{ owner_id: string; email: string; name: string|null; company: string|null;
  picture: string|null; plan: string; profile_completed: boolean;
  created_at: string; updated_at: string }
```

**Projects**

```
POST   /v1/projects              body: { name: string, description?: string } → ProjectPublic  (201)
GET    /v1/projects              → { projects: ProjectPublic[] }
GET    /v1/projects/{id}         → ProjectPublic
DELETE /v1/projects/{id}         → 204   (also revokes all its API keys)
```

`ProjectPublic`:
```ts
{ project_id: string; owner_id: string; name: string; description: string|null;
  plan: string; max_bytes: number; max_files: number;
  created_at: string; updated_at: string }
```

Max 50 projects per owner. Duplicate names return `409`.

**API keys**

```
POST   /v1/projects/{id}/keys            body: { name?: string } → ApiKeyCreated  (201)
GET    /v1/projects/{id}/keys            → { keys: ApiKeyPublic[] }
DELETE /v1/projects/{id}/keys/{key_id}   → ApiKeyPublic (revoked: true)
```

`ApiKeyCreated`:
```ts
{ key: ApiKeyPublic; api_key: string }   // api_key = the plaintext secret
```

`ApiKeyPublic`:
```ts
{ key_id: string; project_id: string; name: string|null; key_hint: string;
  revoked: boolean; last_used_at: string|null; created_at: string }
```

**This is the most important UX detail in the whole app:** `api_key` (the
plaintext, e.g. `ZTG_live_xY9kL2mNpQ7rS4tU8vW1xZ3aB6cD0eF5gH`) is returned
**exactly once**, by the POST. It can never be retrieved again — the backend
only stores a hash. Show it in a modal with a copy button and a clear warning
like *"Save this now. You will not be able to see it again."* The list endpoint
only ever returns `key_hint` (last 4 chars) for display, e.g. `ZTG_live_••••f4c1`.

Max 20 active keys per project.

**Usage**

```
GET /v1/projects/{id}/usage → UsagePublic
```

```ts
{ project_id: string; total_files: number; total_bytes: number;
  uploads: number; downloads: number; streams: number;
  bandwidth_out_bytes: number; api_requests: number;
  quota_bytes: number; quota_files: number;
  bytes_remaining: number; files_remaining: number; updated_at: string }
```

**Health**

```
GET /health → { status, service, env, storage_backend }
```

---

## The file endpoints are NOT for this dashboard

```
POST   /v1/files
GET    /v1/files/{id}
GET    /v1/files/{id}/download
GET    /v1/files/{id}/stream
...
```

These authenticate with `Authorization: Bearer ZTG_live_...`, **not** a Firebase
token. They are for the owner's own application server.

**Never call them from the dashboard browser code.** Doing so would require
shipping an API key to the browser, where any visitor could read it from
DevTools. If you want a file browser in the dashboard later, the backend needs
a new Firebase-authenticated listing endpoint — do not work around it.

Instead, the dashboard should **document** these endpoints for the owner:
show copy-paste `curl` and JS snippets on the project page so they know how to
use their key in their own backend.

---

## Pages to build

1. **Landing / Login** — product pitch, one "Continue with Google" button.
2. **Complete Profile** — Name + Company. Only shown when
   `requires_profile_completion` is true. Cannot be skipped.
3. **Dashboard home** — project list, quick usage summary, "New Project".
4. **Project detail** — usage stats with a quota progress bar, API keys table,
   "Create key" button, and an integration snippet section showing how to
   upload/download/stream with their key.
5. **Settings** — profile (name, company, email, plan), sign out.

## UI requirements

- Responsive, works on mobile.
- Dark mode friendly.
- Real loading skeletons, not spinners on everything.
- Empty states with a clear next action ("No projects yet — create one").
- Every destructive action (delete project, revoke key) gets a confirm dialog
  that names the thing being deleted.
- Format bytes as KB/MB/GB, timestamps as relative ("2 hours ago") with the
  full ISO value in a tooltip.
- Quota bar changes colour past 80% and 95%.

## Code requirements

- Keep all API calls in one `lib/api.ts` module with typed functions. No
  `fetch` scattered through components.
- Keep Firebase setup in one `lib/firebase.ts`.
- Define the TypeScript interfaces exactly as specified above.
- Put the base URL in an env var.
- An `AuthProvider` context exposing `{ user, owner, loading, signIn, signOut }`,
  built on `onAuthStateChanged`.
- Route guard: unauthenticated → login page; authenticated but
  `profile_completed === false` → profile form; otherwise → dashboard.

## Do not

- Do not implement Google OAuth manually — use the Firebase Web SDK.
- Do not build a backend login page or an OAuth callback route.
- Do not store the Firebase ID token or an API key in `localStorage`.
- Do not call `/v1/files/*` from the browser.
- Do not invent endpoints. If something seems missing, say so instead of
  guessing.
- Do not display `owner_id`, `project_id` or `key_id` as primary UI — they are
  for debugging and copy buttons, not headlines.

Start by telling me the file structure you plan to create, then write the code.

---
