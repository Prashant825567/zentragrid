Build the complete frontend for my existing backend product "ZentraGrid".

IMPORTANT:
This is a complete frontend generation request.
Use the backend API contract below exactly.
Do not invent API routes.
Do not modify backend behavior.
Build the frontend around the documented API.

==================================================
BRAND
==================================================

Name:
ZentraGrid

Product:
Developer storage infrastructure for modern applications.

Tagline:
"Storage infrastructure for modern applications."

The visual identity should be premium, futuristic, technical and highly polished.

==================================================
DESIGN LANGUAGE — LIQUID GLASS EVERYWHERE
==================================================

The entire website must use a consistent LIQUID GLASS design language.

Every major UI surface should feel like translucent liquid glass.

Use liquid glass for:

- navbar
- buttons
- cards
- feature panels
- code panels
- dialogs
- dropdowns
- dashboard widgets
- tables
- sidebars
- modals
- authentication forms
- documentation navigation
- pricing cards
- settings panels
- file detail panels
- API key dialogs
- toast notifications

Do NOT make the UI look like ordinary flat dark cards.

The liquid-glass effect should include:

- translucent surfaces
- backdrop blur
- subtle internal highlights
- soft refraction-like gradients
- thin luminous borders
- subtle depth
- layered transparency
- realistic shadows
- soft ambient glow

Keep the liquid-glass treatment elegant and restrained.

Do not use huge blurry blobs behind every card.

==================================================
COLOUR SYSTEM
==================================================

Primary background:
#06070B

Secondary background:
#0B0D14

Glass surface:
rgba(255,255,255,0.06)

Glass border:
rgba(255,255,255,0.12)

Primary accent:
#FF4FD8

Secondary pink:
#FF2FB3

Soft pink:
#FF9BE8

Secondary accent:
#8B5CF6

Optional technical highlight:
#67E8F9

Primary text:
#F8FAFC

Secondary text:
#CBD5E1

Muted text:
#94A3B8

Pink should be the dominant brand accent.

Violet and cyan are secondary accents only.

Avoid:
- rainbow gradients
- excessive neon
- crypto aesthetics
- gaming aesthetics
- childish colors
- flat generic SaaS cards

==================================================
TECH STACK
==================================================

Use:

- Next.js
- React
- TypeScript
- Tailwind CSS
- Three.js
- React Three Fiber
- @react-three/drei
- Anime.js
- Firebase Web SDK
- Lucide React

Use modern Next.js architecture.

Use reusable components.

Use strong TypeScript typing.

==================================================
3D + ANIMATION RULE
==================================================

Three.js / React Three Fiber:
Use for actual live 3D scenes.

Anime.js:
Use for HTML/UI motion.

Do not use Anime.js as a replacement for the Three.js 3D renderer.

==================================================
SITE STRUCTURE
==================================================

Create these public pages:

/
/features
/pricing
/security
/about
/contact
/status

Authentication:

/login
/signup
/forgot-password

NOTE ON AUTH ROUTES:
The backend supports Google Sign-In ONLY. There are no passwords, no
email-link sign-in and no password-reset endpoints.

/login            -> a single "Continue with Google" button
/signup           -> identical to /login. Signup happens automatically on
                     first Google sign-in. Point this route at the same
                     component or redirect it to /login.
/forgot-password  -> there are no passwords. Make this a short liquid-glass
                     page explaining that ZentraGrid uses Google Sign-In,
                     with a link back to /login.

Do not build email/password forms anywhere.

Dashboard:

/dashboard
/dashboard/projects
/dashboard/projects/[project_id]
/dashboard/api-keys
/dashboard/storage
/dashboard/storage/[file_id]
/dashboard/usage
/dashboard/billing
/dashboard/settings

Documentation:

/docs
/docs/getting-started
/docs/authentication
/docs/projects
/docs/files
/docs/files/upload
/docs/files/download
/docs/files/delete
/docs/files/rename
/docs/files/streaming
/docs/api
/docs/api-reference
/docs/errors
/docs/rate-limits
/docs/examples

Legal:

/privacy
/terms
/acceptable-use
/cookies

Error pages:

/404
/500

==================================================
GLOBAL NAVBAR
==================================================

Create a premium liquid-glass sticky navbar.

Left:
ZentraGrid logo + wordmark

Navigation:
Products
Developers
Pricing
Security

Right:
Login
Get Started

On scroll:
- glass becomes slightly more opaque
- blur increases
- border becomes visible
- subtle pink highlight appears

Use Anime.js for:
- menu entrance
- link hover
- CTA motion

Mobile:
Use a liquid-glass fullscreen/drawer navigation.

==================================================
HOME PAGE
==================================================

Hero should be the signature experience of ZentraGrid.

Layout:

LEFT:
Large typography and CTA.

RIGHT:
LIVE INTERACTIVE 3D infrastructure scene.

Badge:

"Developer Storage Infrastructure"

Headline:

"Storage infrastructure for modern applications."

Highlight:
"Storage infrastructure"

Use liquid pink/violet gradient only on this phrase.

Description:

"Upload, store, stream, and serve your application's files through a simple developer-first API."

Buttons:

Get Started
View Documentation

==================================================
LIVE 3D HERO
==================================================

Use React Three Fiber + Three.js.

Create a live 3D storage infrastructure visualization.

Scene:

A central glowing storage core.

Around it:

Application
API Gateway
Storage
Delivery

Connect these nodes using curved data paths.

Animate small data packets traveling through the paths.

Use subtle:
- particles
- depth
- grid
- atmosphere
- perspective
- soft lighting
- floating data/file elements

The 3D visual must communicate:

Application
→ API Gateway
→ Storage
→ Delivery

This must look like infrastructure, not a random abstract 3D object.

==================================================
3D INTERACTION
==================================================

Mouse:
- subtle camera parallax
- smooth camera follow
- nodes react slightly

Node hover:
- glow increases
- connection becomes brighter
- tooltip appears
- node slightly scales up

Tooltip examples:

API Gateway
Authenticated developer requests

Storage Node
Application file storage

Delivery Layer
File delivery and streaming

Application
Connected application

==================================================
3D PERFORMANCE
==================================================

Important:

- dynamic import the 3D scene
- lazy load where appropriate
- cap device pixel ratio
- low/medium-poly geometry
- limited particles
- no unnecessary React rerenders
- reduce effects on low-power devices
- simplify scene on mobile
- fallback if WebGL unavailable

The site should run reasonably well on integrated graphics.

Respect prefers-reduced-motion.

==================================================
LIQUID GLASS HERO UI
==================================================

Place a large floating liquid-glass panel partially overlapping the 3D scene.

Panel should display live-looking demo infrastructure information:

Storage Nodes
4 active

Data Flow
Operational

API Requests
12.4K demo

Delivery
Ready

Clearly label demo values as example/demo data.

Add tiny animated status indicators.

==================================================
CAPABILITY STRIP
==================================================

Create a liquid-glass horizontal section:

Simple API
File Storage
Media Delivery
Video Streaming
API Authentication
Usage Monitoring

Use subtle Anime.js stagger.

==================================================
FEATURES
==================================================

Heading:

"Everything your application needs for file storage."

Create six liquid-glass feature panels.

Developer API
File Storage
Media Delivery
Video Streaming
API Authentication
Usage Monitoring

Use:
- hover depth
- pink edge glow
- subtle cursor response
- Anime.js entrance

==================================================
API SHOWCASE
==================================================

Create a large liquid-glass developer panel.

Heading:

"Your storage layer, exposed through an API."

Example:

POST /v1/files

Authorization: Bearer ZTG_********

Content-Type: multipart/form-data

Response:

{
  "id": "file_abc123",
  "name": "video.mp4",
  "size": 48293120,
  "mime_type": "video/mp4",
  "status": "active"
}

Add:
- code highlighting
- copy button
- line numbers
- animated code appearance

Clearly label as example code.

==================================================
HOW IT WORKS
==================================================

Four steps:

01 Create a project
02 Generate an API key
03 Upload your files
04 Serve files through your application

Use liquid-glass step cards.

Connect the steps with animated lines.

==================================================
DASHBOARD PREVIEW
==================================================

Create a beautiful liquid-glass dashboard preview.

Demo metrics:

Storage:
18.4 GB

Bandwidth:
42.8 GB

API Requests:
128,492

Files:
12,840

Label:
Example dashboard data

Include:
- graph
- usage meter
- recent files
- activity feed

==================================================
SECURITY SECTION
==================================================

Heading:

"Built with developer control in mind."

Liquid-glass panels:

API Key Authentication
Project Isolation
Access Control
Rate Limiting
Usage Monitoring

Avoid unsupported certifications or guarantees.

==================================================
PRICING
==================================================

Three liquid-glass pricing cards:

Free
Developer
Business

Use configurable placeholder pricing.

Do not invent fake statistics or customer claims.

==================================================
FINAL CTA
==================================================

Headline:

"Build your storage layer with ZentraGrid."

Description:

"Connect your application to a developer-focused storage API."

Buttons:

Get Started
Explore Documentation

Use a subtle animated 3D grid behind the CTA.

==================================================
FOOTER
==================================================

Use liquid-glass footer panels.

ZentraGrid

Storage infrastructure for modern applications.

Product:
Features
Pricing
Security

Developers:
Documentation
API Reference
Examples
Getting Started

Company:
About
Contact
Support
Status

Legal:
Privacy
Terms
Acceptable Use
Cookies

© 2026 ZentraGrid

==================================================
FIREBASE GOOGLE AUTHENTICATION
==================================================

Use Firebase Authentication for:

"Continue with Google"

Firebase client config — use this EXACT object, character for character:

const firebaseConfig = {
  apiKey: "AIzaSyBVYRNNyBxtXfLCXFTUFB-XH1ggNl030u4",
  authDomain: "zentragrid.firebaseapp.com",
  projectId: "zentragrid",
  storageBucket: "zentragrid.firebasestorage.app",
  messagingSenderId: "873269002556",
  appId: "1:873269002556:web:9f14acabe4403eb3001e39",
  measurementId: "G-5TYYQRFRZ3"
};

This apiKey is a public client identifier, not a secret. It is safe in
frontend code.

Use only for frontend Firebase initialization.

Never place Firebase Admin credentials in the frontend.

==================================================
WHERE GOOGLE SIGN-IN RUNS
==================================================

Google Sign-In runs entirely in the FRONTEND. The backend only verifies the
resulting token.

BROWSER (your code)                        BACKEND (already built)
-------------------                        -----------------------
1. User clicks "Continue with Google"
2. Firebase opens the Google popup
3. User picks an account
4. Firebase returns a User object
5. await user.getIdToken()
6. fetch(..., {                 --------->
     Authorization: `Bearer ${idToken}`
   })                                      7. Verifies the signature against
                                              Google's PUBLIC keys
                                           8. Finds or creates the owner
                                  <------- 9. Returns the owner record

The backend has NO login page, NO OAuth callback route and NO code exchange.
Do not build one. Do not implement OAuth by hand — use the Firebase Web SDK.

There are no session cookies. Every request carries a fresh Firebase ID token
in the Authorization header.

TOKEN RULES:
- Call await user.getIdToken() before every API request. Firebase caches and
  auto-refreshes it, so this is cheap and correct.
- Tokens expire after 1 hour. Never persist one in localStorage yourself.
- Use onAuthStateChanged to restore the session on reload. Hold a loading
  state until it fires — never flash the login page at a signed-in user.
- On 401: retry once with getIdToken(true). If it fails again, sign out.

GOOGLE LOGIN FLOW:

User clicks:
Continue with Google

Firebase:
signInWithPopup()

Then:

user.getIdToken()

Send:

POST /v1/auth/google

Header:

Authorization: Bearer <FIREBASE_ID_TOKEN>

Body:

{}

==================================================
FIRST-TIME OWNER FLOW
==================================================

After Google login:

If:

requires_profile_completion = true

Show liquid-glass onboarding page/modal:

Name
Company

Submit:

PATCH /v1/auth/me

Body:

{
  "name": "...",
  "company": "..."
}

Then open dashboard.

If owner already exists:

Do not ask name again.

Load existing profile and continue directly to dashboard.
Use the stored name/company from the response, not the Google display name —
the stored profile always wins.

IMPORTANT — A DEFAULT PROJECT ALREADY EXISTS:
The backend automatically creates a default project the moment the owner
completes their profile. After PATCH /v1/auth/me, GET /v1/projects already
returns one project.

Do NOT create a project during onboarding — you would end up with two. The
dashboard must never show a "create your first project" empty state right
after signup.

==================================================
DASHBOARD AUTH
==================================================

Dashboard routes use:

Authorization: Bearer <FIREBASE_ID_TOKEN>

Developer file routes DO NOT use Firebase token.

==================================================
BACKEND API CONTRACT
==================================================

The frontend MUST use these exact backend routes.

BASE API URL should come from an environment variable:

NEXT_PUBLIC_API_BASE_URL

Do not hardcode production URL.
Use http://localhost:8000 as the local development fallback.

==================================================
ROOT / HEALTH
==================================================

GET /

Service information.

GET /health

Service liveness endpoint.

Response:
{ "status": "ok", "service": "ZentraGrid", "env": "...", "storage_backend": "..." }

GET /health/ready

Readiness. Exact response shape:

{
  "status": "ready" | "degraded",
  "storage": { "backend": string, "connected": boolean, "authorized": boolean },
  "auth_mode": "admin" | "jwks" | "insecure" | "unconfigured",
  "auth_ready": boolean,
  "firebase_project_id": string | null,
  "service_account_key": boolean
}

Use this for the /status page. "storage.backend" is an internal implementation
detail — show a friendly label such as "Storage" and "Operational" /
"Degraded", never the raw backend name.

==================================================
DASHBOARD AUTH ROUTES
==================================================

POST /v1/auth/google

Purpose:
Google login/signup.

Authentication:
Firebase ID token.

Body: {}

Response:
{
  "owner": Owner,
  "is_new_owner": boolean,
  "requires_profile_completion": boolean
}

Expected behavior:
First login can require profile completion.
Existing owner goes directly to dashboard.
Signing in repeatedly never creates a duplicate account — the backend matches
on email first, then Firebase UID.

GET /v1/auth/me

Purpose:
Current owner profile. Returns Owner.

PATCH /v1/auth/me

Purpose:
Update name/company during profile completion.

Body: { "name": string, "company"?: string }
Returns Owner.

Authentication:
Firebase ID token.

==================================================
PROJECT ROUTES
==================================================

POST /v1/projects

Create project.
Body: { "name": string, "description"?: string }
Returns Project (201).

GET /v1/projects

List owner's projects.
Returns { "projects": Project[] }

GET /v1/projects/{project_id}

Get one project. Returns Project.

DELETE /v1/projects/{project_id}

Delete project and revoke its API keys. Returns 204.

Authentication:
Firebase ID token.

==================================================
API KEY ROUTES
==================================================

POST /v1/projects/{project_id}/keys

Create new API key.
Body: { "name"?: string }
Returns { "key": ApiKey, "api_key": string } (201)

Plaintext key is returned only once.

GET /v1/projects/{project_id}/keys

List project keys.
Returns { "keys": ApiKey[] }

Do not display plaintext.

DELETE /v1/projects/{project_id}/keys/{key_id}

Revoke key. Returns ApiKey with revoked: true.

Authentication:
Firebase ID token.

IMPORTANT — THERE IS NO GLOBAL KEYS ENDPOINT:
API keys exist ONLY under a project. The three routes above are the only key
routes. There is no GET /v1/keys and no global key list.

So the /dashboard/api-keys page must:
  - first call GET /v1/projects
  - then call GET /v1/projects/{id}/keys for each project
  - merge the results client-side, showing the project name per row
  - run those calls in parallel (Promise.all), not in a sequential loop

Creating a key always requires choosing a project first.

==================================================
USAGE
==================================================

GET /v1/projects/{project_id}/usage

Returns exactly these fields:

  project_id, total_files, total_bytes, uploads, downloads, streams,
  bandwidth_out_bytes, api_requests, quota_bytes, quota_files,
  bytes_remaining, files_remaining, updated_at

IMPORTANT — THESE ARE CUMULATIVE LIFETIME COUNTERS, NOT TIME SERIES:
There is no per-day breakdown and no history array, so the backend cannot
support 24h / 7d / 30d / 90d filters.

For /dashboard/usage:
  - show the real numbers as stat cards, quota progress bars and simple
    ratio charts (bytes used vs quota, files used vs quota)
  - do NOT render a time-series line chart from invented data points
  - if you include time-range controls for future use, disable them and
    label them clearly as not yet available

Authentication:
Firebase ID token.

==================================================
DEVELOPER FILE API
==================================================

These routes use:

Authorization: Bearer ZTG_live_xxx

NOT Firebase tokens. A Firebase ID token is rejected on all of them with 401.

==================================================
CRITICAL — THE BROWSER CANNOT CALL THE FILE ENDPOINTS
==================================================

This is the most important architectural constraint in this build.

The backend stores only a HASH of every API key. The plaintext is returned
once at creation and is never retrievable again. Therefore the dashboard
cannot hold a usable API key, and these routes cannot be called from browser
code.

Do NOT build /dashboard/storage or /dashboard/storage/[file_id] as pages that
call the backend directly from the client.

Do NOT ask the user to paste their API key into the browser to make it work —
that leaks the secret into DevTools, localStorage and browser history.

Instead, implement the storage pages through Next.js Route Handlers acting as
a server-side proxy:

  app/api/proxy/files/route.ts                      -> POST + GET  /v1/files
  app/api/proxy/files/[file_id]/route.ts            -> GET, PATCH, DELETE
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

==================================================
UPLOAD
==================================================

POST /v1/files

multipart/form-data

Form fields:
  file       required, the binary
  filename   optional, override the stored name
  metadata   optional, JSON object, max 32 flat keys

Upload file.

Show real upload progress in UI.

After success:
display returned file_id and metadata.

Response (201):
{
  "id": "file_abc123",
  "name": "video.mp4",
  "size": 48293120,
  "mime_type": "video/mp4",
  "status": "active"
}

Max upload size is 2 GiB. Above that the backend returns
413 PAYLOAD_TOO_LARGE.

==================================================
LIST + SEARCH
==================================================

GET /v1/files

Supported query parameters — these three ONLY:

  query    string, optional, max 120 chars, matches "filename contains"
  limit    integer, 1-200, default 50
  cursor   string, optional, opaque pagination cursor

Response:
{ "files": FilePublic[], "next_cursor": string | null }

There is NO sort parameter, NO type/MIME filter and NO date-range filter.

UI must support:
- list
- search (via the query parameter)
- filtering and sorting done CLIENT-SIDE on the returned page only
- cursor-based pagination using next_cursor, not page numbers

Do not build UI controls that imply server-side sorting or filtering that
does not exist.

==================================================
FILE METADATA
==================================================

GET /v1/files/{file_id}

Returns FilePublic:

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

Show:

file ID
filename
size
MIME type
status
created timestamp
uploaded_by_key_id — useful when rotating or investigating a leaked key

==================================================
RENAME
==================================================

PATCH /v1/files/{file_id}

Body:

{
  "name": "new-name.mp4"
}

Create an elegant inline rename interaction.

This renames only the ZentraGrid metadata filename. The stored object itself
is untouched.

==================================================
DELETE
==================================================

DELETE /v1/files/{file_id}

Show confirmation liquid-glass modal.

After success:
remove item from current UI.

==================================================
DOWNLOAD
==================================================

GET /v1/files/{file_id}/download

Provide download interaction.

Streamed response, never buffered whole in memory.

Never expose developer API secrets unnecessarily in browser code — route this
through the proxy handler described above.

==================================================
STREAM
==================================================

GET /v1/files/{file_id}/stream

Video streaming endpoint.

Backend supports Range requests and returns:

  206 Partial Content
  Accept-Ranges: bytes
  Content-Range: bytes 0-1048575/48293120
  Content-Length: 1048576
  Content-Type: video/mp4

Supported forms: bytes=start-end, bytes=start-, suffix bytes=-N.
A single range response is capped at 16 MiB; players simply request the next
range. Unsatisfiable ranges return 416 RANGE_NOT_SATISFIABLE.

Build a video player UI capable of seeking.

Do not assume the backend supports every browser-specific behavior; handle
errors gracefully.

==================================================
IMPORTANT SECRET RULE
==================================================

Developer API keys must NEVER be exposed as public frontend credentials.

The dashboard may display:
- key hint
- creation date
- revoked status

The actual secret is shown only once when created.

For the dashboard, if direct browser calls to developer file endpoints would
expose a project secret, do not do that.

The architecture should keep sensitive developer credentials server-side or
provide a secure proxy approach.

==================================================
TYPESCRIPT TYPES — COPY THESE EXACTLY
==================================================

interface Owner {
  owner_id: string;
  email: string;
  name: string | null;
  company: string | null;
  picture: string | null;
  plan: string;
  profile_completed: boolean;
  created_at: string;
  updated_at: string;
}

interface Project {
  project_id: string;
  owner_id: string;
  name: string;
  description: string | null;
  plan: string;
  max_bytes: number;
  max_files: number;
  created_at: string;
  updated_at: string;
}

interface ApiKey {
  key_id: string;
  project_id: string;
  name: string | null;
  key_hint: string;            // last 4 chars only
  revoked: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface ApiKeyCreated {
  key: ApiKey;
  api_key: string;             // PLAINTEXT — returned exactly once, ever
}

interface FilePublic {
  id: string;
  name: string;
  project_id: string;
  owner_id: string;
  mime_type: string;
  size: number;
  status: string;
  uploaded_by_key_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface Usage {
  project_id: string;
  total_files: number;
  total_bytes: number;
  uploads: number;
  downloads: number;
  streams: number;
  bandwidth_out_bytes: number;
  api_requests: number;
  quota_bytes: number;
  quota_files: number;
  bytes_remaining: number;
  files_remaining: number;
  updated_at: string;
}

==================================================
LIMITS THE UI MUST ENFORCE
==================================================

  Projects per owner            50
  Active API keys per project   20
  Project name                  120 chars
  Project description           500 chars
  Owner name                    120 chars
  Company                       160 chars
  API key label                 80 chars
  Max upload size               2 GiB

Show character counters approaching the limit and disable submit past it.
Exceeding the project or key count returns 409 CONFLICT — surface the message.

==================================================
DASHBOARD
==================================================

Create a premium liquid-glass dashboard.

Sidebar:

Overview
Projects
Storage
API Keys
Usage
Billing
Documentation
Settings

Topbar:
Owner avatar
Owner name
Project selector
Notifications
Logout

==================================================
DASHBOARD OVERVIEW
==================================================

Route:

/dashboard

Show:

Storage Used
Bandwidth
API Requests
Files

Pull real values by calling GET /v1/projects/{id}/usage for the selected
project. Demo data only where no live API data exists — and label it.

Use animated graphs.

==================================================
PROJECTS
==================================================

/dashboard/projects

Functions:

Create Project
Open Project
Delete Project

Liquid-glass project cards.

Deleting a project also revokes every API key under it — say this explicitly
in the confirmation modal.

==================================================
PROJECT DETAILS
==================================================

/dashboard/projects/[project_id]

Show:
Project name
Project ID
API keys
Usage
Storage summary

Also include an integration snippets section with copy-paste curl, JavaScript
and Python examples showing how the owner uses their key from their OWN
backend, with the real base URL filled in.

==================================================
API KEYS
==================================================

/dashboard/api-keys

Remember: there is no global keys endpoint. Fetch projects first, then each
project's keys in parallel, then merge.

Show:
Key hint
Project
Created
Status
Last used if available

Create Key modal:
Explain plaintext is shown only once.

Use:
Copy
Reveal
Done

The reveal modal must NOT be dismissible by clicking the backdrop — the user
must explicitly press Done. Losing this value is unrecoverable.

After closing, never display full secret again.
Everywhere else render keys as ZTG_live_••••••••f4c1 using key_hint.

==================================================
STORAGE
==================================================

/dashboard/storage

Route every call through the server-side proxy handlers described earlier.

Show:

Upload button
Search field
Filter
Sort

Table/list columns:

Name
Type
Size
Status
Created
Actions

Actions:

Open
Rename
Download
Delete

Use liquid-glass table.

Remember: search maps to the query parameter; filter and sort are client-side
on the current page only.

==================================================
FILE DETAILS
==================================================

/dashboard/storage/[file_id]

Show:
Preview
Filename
File ID
MIME type
Size
Created time
Status
Uploaded by key

Actions:
Rename
Download
Delete
Stream video

==================================================
USAGE
==================================================

/dashboard/usage

Show real cumulative counters as stat cards and quota progress bars.

Storage
Bandwidth
API requests
File count

Time-range filters (24h / 7d / 30d / 90d) are NOT supported by the backend.
Either omit them, or render them disabled and labelled as coming soon.
Never invent time-series data.

==================================================
BILLING
==================================================

/dashboard/billing

There are no billing, invoice, payment-method or plan-change endpoints. The
owner and project objects carry a "plan" string field and nothing more.

Build this as a read-only page showing:
- current plan from owner.plan
- quota usage from the usage endpoint

Label anything else as coming soon. Do not build invoice tables or payment
forms filled with fake data.

Do not implement real payments unless an actual payment backend exists.

==================================================
SETTINGS
==================================================

/dashboard/settings

Sections:

Profile
Security
Sessions
Account

Profile edits use PATCH /v1/auth/me.

Danger zone:
Delete account — there is no delete-account endpoint. Render it disabled with
a "contact support" note rather than wiring it to a route that does not exist.

==================================================
DOCUMENTATION
==================================================

Create premium documentation UI using the same liquid-glass design.

Routes:

/docs
/docs/getting-started
/docs/authentication
/docs/projects
/docs/files
/docs/files/upload
/docs/files/download
/docs/files/delete
/docs/files/rename
/docs/files/streaming
/docs/api-reference
/docs/errors
/docs/rate-limits
/docs/examples

Left sidebar.

Main content.

Right-side table of contents on desktop.

Code blocks should match ZentraGrid visual identity.

Copy buttons.

Search UI.

==================================================
DOCUMENTATION CONTENT
==================================================

Authentication explains:

Dashboard:

Authorization: Bearer <FIREBASE_ID_TOKEN>

Developer API:

Authorization: Bearer ZTG_live_xxx

Explicitly explain that they are different authentication systems.

Make clear that the developer API key belongs on the customer's own server,
never in browser code.

Rate limits page — these are configurable defaults, not guarantees:

  Upload      30 requests/min
  Download    120 requests/min
  Stream      240 requests/min
  General     300 requests/min
  Dashboard   120 requests/min

Exceeding a limit returns 429 with a Retry-After header.

==================================================
ERROR UI
==================================================

Every error response from the backend is exactly:

{ "error": { "code": string, "message": string } }

Write ONE apiFetch helper that attaches the token, unwraps this envelope and
throws a typed ApiError { code, message, status }. Do not scatter error
handling.

Complete code list:

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

Handle:

400
401
403
404
409
413
429
500

Create beautiful liquid-glass error states.

Especially:

403 PROFILE_INCOMPLETE

Display appropriate onboarding CTA.

Note: cross-tenant access deliberately returns 404, never 403, so resource
ids cannot be enumerated. Treat a 404 on someone else's resource as normal.

==================================================
LOADING STATES
==================================================

Create:
- glass skeleton loaders
- animated shimmer
- route loading
- upload progress
- delete loading
- rename saving
- project creation loading

==================================================
TOASTS
==================================================

Liquid-glass toast notifications:

Success
Error
Warning
Info

Use subtle Anime.js entrance/exit.

==================================================
RESPONSIVE
==================================================

Desktop:
Full 3D hero
Full dashboard sidebar

Tablet:
Simplified 3D

Mobile:
Reduced 3D
Mobile navigation
Stacked cards
Horizontal scrolling only where appropriate
No horizontal page overflow

==================================================
ACCESSIBILITY
==================================================

Implement:

- semantic HTML
- keyboard navigation
- visible focus states
- accessible labels
- sufficient contrast
- reduced-motion support

Note on glass surfaces: body text must hit 4.5:1 against the BLURRED backdrop,
not against the tint colour alone. Where it does not, add a subtle darker
scrim behind the text inside the glass surface.

==================================================
SEO
==================================================

Homepage:

Title:
ZentraGrid — Storage Infrastructure for Modern Applications

Description:
Developer-focused storage infrastructure for uploading, storing, streaming, and serving application files.

Add Open Graph metadata.

==================================================
BACKEND INTEGRATION
==================================================

Create a central API client:

lib/api/

with typed functions such as:

authApi
projectsApi
keysApi
filesApi
usageApi

Do not scatter fetch logic everywhere.

Use environment:

NEXT_PUBLIC_API_BASE_URL

Example:

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

==================================================
AUTH STATE
==================================================

Create a clean auth provider/hook.

Example:

useAuth()

It should provide:

user
owner
loading
signInWithGoogle
logout
idToken

Handle token refresh using Firebase.

Route guard:
- signed out                        -> landing / login
- signed in, profile_completed=false -> onboarding form
- otherwise                          -> dashboard

==================================================
ENVIRONMENT VARIABLES
==================================================

NEXT_PUBLIC_API_BASE_URL   the backend base URL, e.g. http://localhost:8000
                           during development

ZENTRAGRID_API_KEY         server-only ZTG_live_ key used by the proxy route
                           handlers. MUST NOT be prefixed NEXT_PUBLIC_.

Never place a ZTG_live_ key, a Firebase private key, or any storage backend
credential in a NEXT_PUBLIC_ variable or anywhere in client code.

==================================================
SECURITY
==================================================

Never:

- expose the storage backend session or credentials
- expose Firebase Admin credentials
- log Firebase tokens
- log developer API keys
- put secrets into NEXT_PUBLIC_ variables
- trust owner_id from the browser
- trust project ownership from browser input

Use Firebase ID token for dashboard identity.

==================================================
INTERNAL IMPLEMENTATION — NEVER SURFACE THIS
==================================================

The backend persists data in private storage channels rather than a
traditional database. This is an internal detail and the API already strips
every internal id from responses.

Never surface the storage implementation, channel ids or message ids anywhere
in the UI, documentation, code comments or status page. To the user this is
simply "ZentraGrid storage".

==================================================
FINAL VISUAL GOAL
==================================================

This should be a premium next-generation developer storage platform.

The signature identity should be:

DARK BACKGROUND
+
PINK LIQUID GLASS
+
SUBTLE VIOLET
+
LIVE 3D INFRASTRUCTURE
+
SMOOTH ANIME.JS MOTION
+
DEVELOPER-FOCUSED UX

Do not make every animation huge.

Do not use generic template illustrations.

Do not use fake customer logos.

Do not use fake testimonials.

Do not use fake statistics.

Do not invent backend routes.

Use the exact API contract above.

Before generating code:
1. Inspect the existing project structure.
2. Create reusable UI components.
3. Create the API client layer.
4. Create the auth layer.
5. Create the public pages.
6. Create the authentication pages.
7. Create the dashboard.
8. Create the documentation.
9. Create legal/status/error pages.

The final result should feel like a real premium developer infrastructure
startup rather than a generated template.

Start by showing me the file tree, then wait for my confirmation before
writing the rest.
