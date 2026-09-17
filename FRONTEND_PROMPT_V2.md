# ZentraGrid Frontend — Full Build Prompt

Paste everything below the line into Google AI Studio.

---

You are building the complete frontend for **ZentraGrid** from scratch: a
reusable "liquid glass" component library in pink, plus the dashboard that uses
it. React + TypeScript + Tailwind CSS.

The backend is already built, deployed and working. Do not redesign it, do not
invent endpoints, do not change the contract. Read the backend section
carefully — the UI must mirror how it actually behaves.

---

# PART 1 — What ZentraGrid is and how the backend works

## The product in one paragraph

ZentraGrid sells storage infrastructure to startups. Imagine a founder who
built an Instagram-like app; their users upload photos and videos, and they
need somewhere to put all that content. Instead of setting up S3, they sign in
to ZentraGrid with Google, generate an API key, drop that key into their own
backend, and their app uploads through the ZentraGrid REST API. To them it
feels like a normal storage API — they never see what's underneath.

## What's underneath (context only — never show this in the UI)

There is **no SQL or NoSQL database.** Persistence is three private Telegram
channels:

| Channel | Holds |
|---|---|
| **FILES** | The actual uploaded blobs |
| **METADATA** | One JSON record per file, pointing at its blob |
| **OWNERS** | Owner records, projects, API-key hashes, plans, quotas, usage |

The browser never touches Telegram, never sees a channel id, never sees a
Telegram message id. The API strips all of it. **Never mention Telegram
anywhere in the UI.** Users experience a normal storage API.

## There is ONE kind of user: the owner

The founder who signs up. That's your user. But they reach the system through
two different doors, and this shapes the whole app:

### Door 1 — The dashboard (what you are building)

A human, in a browser, authenticated with a **Firebase ID token**. They manage
projects, generate API keys, watch usage. They do not touch files here.

### Door 2 — Their app's server (not your concern)

Machine code, authenticated with a **ZentraGrid API key** (`ZTG_live_...`).
This uploads and serves files. It runs on the founder's own backend.

Think of a bank: the dashboard is walking into the branch with your ID; the API
key is the debit card you then use at ATMs. Same person, different door, very
different powers.

## CRITICAL: where Google Sign-In happens

**Google Sign-In runs entirely in the FRONTEND. The backend only verifies the
resulting token.**

This is the single most common thing to get wrong. Get it right.

```
BROWSER (your code)                        BACKEND (already built)
───────────────────                        ───────────────────────
1. User clicks "Continue with Google"
2. Firebase opens the Google popup
3. User picks an account
4. Firebase returns a User object
5. await user.getIdToken()
6. fetch(..., {                 ─────────►
     Authorization: `Bearer ${idToken}`
   })                                      7. Verifies the signature against
                                              Google's PUBLIC keys
                                           8. Finds or creates the owner
                                  ◄─────── 9. Returns the owner record
```

Concretely:

- Install the `firebase` npm package. Call `initializeApp`, `getAuth`,
  `signInWithPopup(auth, new GoogleAuthProvider())`. **All in the browser.**
- The backend has **no login page, no OAuth callback route, no `code`
  exchange.** Do not build one. Do not implement OAuth by hand.
- There are **no session cookies.** Every single request carries a fresh
  Firebase ID token in the `Authorization` header.

### Firebase web config — public, belongs in frontend code

```ts
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

That `apiKey` is a public client identifier, not a secret — it is safe to ship.
Never put a service-account key, private key, or `ZTG_live_` key in frontend
code.

### Token rules

- Call `await user.getIdToken()` **before every API request.** Firebase caches
  and auto-refreshes it, so this is cheap and correct.
- Tokens expire after 1 hour. Never persist one in `localStorage` yourself.
- Use `onAuthStateChanged` to restore the session on reload. Hold a loading
  state until it fires — never flash the login page at a signed-in user.
- On `401`: retry once with `getIdToken(true)`. If it fails again, sign out.

## The sign-in flow, exactly

**First-time user**

1. Click "Continue with Google" → `signInWithPopup`.
2. `POST /v1/auth/google` with body `{}`.
3. Response: `is_new_owner: true`, `requires_profile_completion: true`.
4. **Show a Name + Company form.** It cannot be skipped — the rest of the
   dashboard returns `403 PROFILE_INCOMPLETE` until it's done.
5. `PATCH /v1/auth/me` with `{ name, company }`.
6. Enter the dashboard. **A default project already exists** — the backend
   creates one automatically at this moment. Do not create one yourself.

**Returning user**

1. Same click, same `POST /v1/auth/google`.
2. Response: `is_new_owner: false`, `requires_profile_completion: false`, with
   the stored `name` and `company`.
3. **Go straight to the dashboard. Never ask for their name again.** Use the
   stored `name`/`company` from the response, not the Google display name — the
   stored profile always wins.

Signing in repeatedly never creates a duplicate account. The backend matches on
email first, then Firebase UID.

## API contract

Base URL from an env var (`VITE_API_BASE`). Never hardcode.

Every dashboard request: `Authorization: Bearer <FIREBASE_ID_TOKEN>`

### Error envelope — every failure, without exception

```json
{ "error": { "code": "PROFILE_INCOMPLETE", "message": "Owner profile must be completed..." } }
```

Write one `apiFetch` helper that attaches the token, unwraps this envelope, and
throws a typed `ApiError { code, message, status }`. Full code list:

| HTTP | Code | UI behaviour |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Inline field errors |
| 400 | `BAD_REQUEST` | Toast |
| 401 | `INVALID_ID_TOKEN` | Refresh token once, then sign out |
| 403 | `PROFILE_INCOMPLETE` | Redirect to profile form |
| 403 | `FORBIDDEN` | "Account disabled" screen |
| 404 | `PROJECT_NOT_FOUND` | Toast + back to project list |
| 404 | `API_KEY_NOT_FOUND` | Refresh the key list |
| 409 | `CONFLICT` | Inline (e.g. duplicate project name) |
| 413 | `QUOTA_EXCEEDED` | Upgrade / free-up-space prompt |
| 429 | `RATE_LIMITED` | "Slow down", respect `Retry-After` header |
| 503 | `STORAGE_UNAVAILABLE` | Full-page "temporarily unavailable" |
| 500 | `INTERNAL_ERROR` | Generic error with a retry button |

### Endpoints

```
POST  /v1/auth/google     body {} → { owner, is_new_owner, requires_profile_completion }
GET   /v1/auth/me         → Owner
PATCH /v1/auth/me         body { name, company? } → Owner

POST   /v1/projects                          body { name, description? } → Project (201)
GET    /v1/projects                          → { projects: Project[] }
GET    /v1/projects/{project_id}             → Project
DELETE /v1/projects/{project_id}             → 204  (also revokes all its keys)

POST   /v1/projects/{project_id}/keys        body { name? } → { key, api_key } (201)
GET    /v1/projects/{project_id}/keys        → { keys: ApiKey[] }
DELETE /v1/projects/{project_id}/keys/{key_id} → ApiKey (revoked: true)

GET    /v1/projects/{project_id}/usage       → Usage
GET    /health                               → { status, service, env, storage_backend }
```

### Types — copy these exactly

```ts
interface Owner {
  owner_id: string; email: string;
  name: string | null; company: string | null; picture: string | null;
  plan: string; profile_completed: boolean;
  created_at: string; updated_at: string;
}

interface Project {
  project_id: string; owner_id: string;
  name: string; description: string | null;
  plan: string; max_bytes: number; max_files: number;
  created_at: string; updated_at: string;
}

interface ApiKey {
  key_id: string; project_id: string; name: string | null;
  key_hint: string;            // last 4 chars only
  revoked: boolean;
  last_used_at: string | null; created_at: string;
}

interface ApiKeyCreated {
  key: ApiKey;
  api_key: string;             // PLAINTEXT — returned exactly once, ever
}

interface Usage {
  project_id: string;
  total_files: number; total_bytes: number;
  uploads: number; downloads: number; streams: number;
  bandwidth_out_bytes: number; api_requests: number;
  quota_bytes: number; quota_files: number;
  bytes_remaining: number; files_remaining: number;
  updated_at: string;
}
```

### The single most important UX rule in this app

`api_key` — the plaintext secret like
`ZTG_live_xY9kL2mNpQ7rS4tU8vW1xZ3aB6cD0eF5gH` — is returned **only** in the
`POST .../keys` response. The backend stores only a hash. It can never be
shown again.

So: show it in a prominent modal, with a big copy button and an unmissable
warning — *"Save this now. You will never be able to see it again."* Make the
modal deliberately hard to dismiss by accident (no click-outside-to-close).
Everywhere else, keys render as `ZTG_live_••••••••f4c1` using `key_hint`.

### Limits the UI must enforce

| Thing | Limit |
|---|---|
| Projects per owner | 50 |
| Active API keys per project | 20 |
| Project name | 120 chars |
| Project description | 500 chars |
| Owner name | 120 chars |
| Company | 160 chars |
| API key label | 80 chars |

Show character counters near the limit and disable submit past it.

## The file endpoints are NOT for this dashboard

```
POST /v1/files                GET /v1/files/{file_id}/download
GET  /v1/files/{file_id}      GET /v1/files/{file_id}/stream   ...
```

These authenticate with `Authorization: Bearer ZTG_live_...`, **not** a Firebase
token. They are for the owner's own server.

**Never call them from browser code.** That would mean shipping an API key to
the browser, where any visitor reads it from DevTools in five seconds. If a
file browser is wanted later, the backend needs a new Firebase-authenticated
endpoint — do not work around this.

What the dashboard *should* do is **teach** the owner: on the project page,
render copy-paste `curl`, JavaScript and Python snippets showing how to use
their key from their own backend, with their real project's base URL filled in.

---

# PART 2 — The "Liquid Glass" design system (pink)

Build a reusable component library first, then compose the app from it.

## The feeling

Frosted pink glass panels floating over a deep, softly-lit background. Light
appears to pass *through* each surface and catch on its edges. Restrained, not
gaudy: the glass is the star, the colour is the tint. Think visionOS and
Apple's Liquid Glass, rendered in rose quartz.

Every glass surface must combine:

1. **Translucency** — you can sense what's behind it
2. **Backdrop blur** — that background is diffused, not readable
3. **A thin luminous border** — a bright hairline catching light
4. **An internal top highlight** — a soft gleam just inside the top edge
5. **A refraction gradient** — subtle colour shift across the surface
6. **Layered depth** — outer shadow plus inner glow, never a flat card
7. **Restraint** — if it looks like plastic or neon, dial it back

## Colour system

Put these in `tailwind.config.ts` under `theme.extend.colors`:

```ts
rose: {
  50:  '#fff1f6',  100: '#ffe4ed',  200: '#fecdd9',
  300: '#fda4bd',  400: '#fb7199',  500: '#f43f77',
  600: '#e11d58',  700: '#be123f',  800: '#9f1239',
  900: '#881337',  950: '#4c0519',
},
glass: {
  // surface tints — always used with backdrop-blur
  base:      'rgba(255, 241, 246, 0.08)',
  raised:    'rgba(255, 241, 246, 0.12)',
  overlay:   'rgba(255, 241, 246, 0.16)',
  sunken:    'rgba(76, 5, 25, 0.24)',
  // borders
  edge:      'rgba(255, 205, 217, 0.22)',
  edgeBright:'rgba(255, 241, 246, 0.45)',
  // internal light
  sheen:     'rgba(255, 255, 255, 0.35)',
  glow:      'rgba(244, 63, 119, 0.28)',
},
ink: {
  DEFAULT: '#1a0710',   // page background
  soft:    '#2a0f1b',
  muted:   '#3d1827',
},
```

Text: `text-rose-50` for primary, `text-rose-200/70` for secondary,
`text-rose-300/50` for tertiary.

Semantic: success `#34d399`, warning `#fbbf24`, danger `#fb7185`,
info `#60a5fa` — always desaturated so they sit inside the glass world.

## Page background

Not a flat colour. A deep ink base with two or three large, soft, slow-drifting
radial gradient orbs in rose tones, heavily blurred. This is what the glass
refracts — without it, the blur has nothing to work with and everything looks
flat.

```tsx
<div className="fixed inset-0 -z-10 bg-ink">
  <div className="absolute -top-40 -left-40 h-[36rem] w-[36rem] rounded-full
                  bg-rose-600/25 blur-[140px] animate-drift-slow" />
  <div className="absolute top-1/3 -right-40 h-[32rem] w-[32rem] rounded-full
                  bg-rose-400/18 blur-[130px] animate-drift-slower" />
  <div className="absolute -bottom-40 left-1/4 h-[30rem] w-[30rem] rounded-full
                  bg-fuchsia-600/15 blur-[150px] animate-drift-slow" />
</div>
```

Add a very faint noise/grain overlay (inline SVG `feTurbulence` data URI at
~3% opacity) over the whole page. This is what stops the gradients from
banding and sells the "real material" look.

## The core glass recipe

Every glass surface is built from these layers. Learn it once, reuse everywhere:

```tsx
// 1. The surface itself
"relative overflow-hidden rounded-2xl",
"bg-glass-raised backdrop-blur-xl backdrop-saturate-150",
"border border-glass-edge",

// 2. Outer depth + inner glow, in one shadow stack
"shadow-[0_8px_32px_-8px_rgba(76,5,25,0.5),0_2px_8px_-2px_rgba(76,5,25,0.3),inset_0_1px_0_0_rgba(255,255,255,0.12)]",

// 3. Top sheen — a pseudo-element, not a real div
"before:absolute before:inset-x-0 before:top-0 before:h-px",
"before:bg-gradient-to-r before:from-transparent before:via-glass-sheen before:to-transparent",

// 4. Refraction wash across the body
"after:absolute after:inset-0 after:bg-gradient-to-br",
"after:from-white/[0.07] after:via-transparent after:to-rose-500/[0.05]",
"after:pointer-events-none",
```

Elevation tiers: `sm` = `blur-md` + tighter shadow; `md` = the recipe above;
`lg` = `blur-2xl` + `bg-glass-overlay` + a wider, softer shadow. Modals use
`lg`.

## The 3D feel

Depth comes from light, not from perspective transforms. Use them sparingly:

- Interactive surfaces get `transition-all duration-300 ease-out`
- Hover: lift with `-translate-y-0.5`, brighten the border to
  `border-glass-edgeBright`, and deepen the shadow
- Press: `translate-y-0 scale-[0.98]`, shrink the shadow — it sinks into the page
- Optional on hero cards only: a pointer-tracking tilt, max 6°, with a radial
  highlight following the cursor. Never on list items, never on buttons.
- Everything respects `prefers-reduced-motion` — wrap motion in
  `motion-safe:` variants.

## Components to build

All in `src/components/ui/`, all typed, all forwarding refs, all accepting
`className` merged via a `cn()` helper (`clsx` + `tailwind-merge`).

### `GlassButton`

Variants: `primary` | `secondary` | `ghost` | `danger`
Sizes: `sm` | `md` | `lg`
Props: `loading`, `disabled`, `icon`, `iconPosition`, `fullWidth`

- `primary`: rose gradient fill (`from-rose-500 to-rose-600`) *under* the glass
  layer, so it glows through rather than sitting flat. Brighter border, a rose
  glow in the shadow stack.
- `secondary`: the standard glass recipe, no fill.
- `ghost`: no border, no background until hover.
- `danger`: same as primary but red-shifted, with a slightly stronger glow.
- On hover, sweep a diagonal specular highlight across the surface (a
  translating gradient pseudo-element, ~600ms). This is the signature
  interaction — make it feel like light moving over glass, not a flash.
- `loading` swaps the label for a spinner and locks the width so nothing jumps.
- Visible `focus-visible` ring in `rose-300/60`, offset from the surface.

### `GlassCard`

Props: `elevation` ('sm'|'md'|'lg'), `interactive`, `glow`, `header`, `footer`

Interactive cards lift and brighten on hover. `glow` adds a soft rose halo
behind the card for featured content. Header and footer are separated by
hairline dividers (`border-glass-edge`) rather than solid rules.

### `GlassNav`

A sticky top bar. Starts nearly transparent and increases its blur and tint as
the page scrolls (listen to scroll, interpolate between two classes). Holds the
logo, primary links with an animated active indicator that slides between
items, and a user menu on the right showing the Google avatar.

Mobile: collapses to a hamburger opening a full-height glass drawer with
staggered item entrance.

### `GlassModal`

Props: `open`, `onClose`, `title`, `description`, `size`, `dismissible`

- A blurred, dimmed backdrop (`bg-ink/60 backdrop-blur-md`) that fades in
- The panel scales from `0.96` and fades up over 250ms
- Focus trap, `Escape` to close, scroll lock on the body, restore focus on close
- Proper `role="dialog"`, `aria-modal`, `aria-labelledby`
- When `dismissible` is false, clicking the backdrop must not close it — this
  is what the API-key reveal modal uses

### `GlassInput`

Also `GlassTextarea` and `GlassSelect`, visually consistent.

Props: `label`, `error`, `hint`, `icon`, `maxLength`, `showCount`

- Inset glass: a darker, sunken surface (`bg-glass-sunken`) so it reads as
  carved into the panel rather than floating on it
- The label floats up and shrinks on focus or when filled
- Focus brightens the border and adds a soft rose glow ring
- Error state shifts the border and glow to the danger colour, message below
- `showCount` renders `n / max`, turning amber near the limit

### Also build

`GlassBadge` (status pills — active, revoked, plan tier), `GlassTooltip`,
`GlassProgress` (the quota bar — a glass track with a gradient fill that
shifts rose → amber past 80% → red past 95%), `GlassSkeleton` (shimmering
glass placeholder), `GlassToast` (stacked, auto-dismiss, slide in from the
top-right), `GlassTable` (used for the API keys list), `CopyButton` (copies,
then morphs the icon to a tick for 2 seconds), `GlassCodeBlock` (for the
integration snippets, with a language tab strip and a copy button).

## Accessibility — non-negotiable

Glass UIs fail accessibility unless you are deliberate:

- Body text must hit **4.5:1** against the *blurred* backdrop, not against the
  tint colour alone. Where it doesn't, add a subtle darker scrim behind the
  text inside the glass surface.
- Never communicate state by colour alone — pair with an icon or text.
- Every interactive element needs a visible `focus-visible` ring.
- All motion behind `motion-safe:`.
- Modals and drawers: focus trap, escape, restored focus.
- Semantic HTML throughout — real `<button>`, real `<form>`, real labels.

---

# PART 3 — The app

## Pages

1. **Landing / Sign in** — the pitch, one "Continue with Google" button. Big
   hero glass card, floating gradient orbs, subtle entrance animation.
2. **Complete profile** — Name + Company. Only when
   `requires_profile_completion` is true. Cannot be skipped or navigated past.
3. **Dashboard home** — project grid, an aggregate usage summary, "New project".
4. **Project detail** — usage stats with the quota progress bar, the API keys
   table, "Create key", and an integration snippets section with their real
   base URL and project context filled in.
5. **Settings** — profile (name, company, email, plan), sign out.

## Structure

```
src/
  components/ui/       all Glass* primitives, one file each, barrel index.ts
  components/layout/   AppShell, Background, Nav, Sidebar
  components/feature/  ProjectCard, ApiKeyTable, UsagePanel, KeyRevealModal,
                       IntegrationSnippets, EmptyState
  lib/
    firebase.ts        initializeApp, getAuth, provider
    api.ts             apiFetch + one typed function per endpoint
    types.ts           the interfaces above, verbatim
    format.ts          formatBytes, formatRelativeTime, maskKey
    cn.ts              clsx + tailwind-merge
  context/AuthContext.tsx   { user, owner, loading, signIn, signOut, refreshOwner }
  hooks/               useProjects, useApiKeys, useUsage, useToast, useCopy
  pages/ (or app/)
```

## Behaviour requirements

- Route guard: signed out → landing; signed in but `profile_completed === false`
  → profile form; otherwise → dashboard.
- Loading states are glass skeletons that match the real layout, not spinners.
- Empty states have a clear next action ("No projects yet — create your first").
- Destructive actions (delete project, revoke key) open a confirm modal that
  names the thing and explains the consequence — deleting a project also
  revokes every key under it, so say that.
- `formatBytes` for all sizes; relative timestamps with the full ISO value in a
  tooltip.
- Optimistic updates where safe (renaming), never for key creation or deletion.
- Toast on every mutation, success and failure.

## Do not

- Do not implement Google OAuth by hand — use the Firebase Web SDK.
- Do not build a backend login page or OAuth callback route.
- Do not persist the Firebase token or any API key in `localStorage`.
- Do not call `/v1/files/*` from the browser.
- Do not mention Telegram, channels, or message ids anywhere in the UI.
- Do not surface `owner_id` / `project_id` / `key_id` as headline UI — they
  belong in copy buttons and debug corners.
- Do not invent endpoints. If something appears missing, say so instead of
  guessing.

## Deliver in this order

1. `tailwind.config.ts` with the full colour system, the shadow scale, the
   keyframes, and the `motion-safe` setup.
2. `globals.css` — base layer, the noise overlay, scrollbar styling, font.
3. The `components/ui/` library, with a short usage example per component.
4. `lib/` — firebase, api, types, format, cn.
5. `context/AuthContext.tsx` and the route guard.
6. The five pages.

Start by showing me the file tree and the `tailwind.config.ts`, then wait for
me to confirm before writing the rest.

---
