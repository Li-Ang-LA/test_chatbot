# Claude Code Web Chatbot — Development Plan

## Goal / Context

Build a modern web chatbot UI on top of the user's existing authenticated **Claude Code** CLI session. The product is a multi-session chat application with:

- **Frontend:** React (Vite + TypeScript)
- **Backend:** FastAPI (Python)
- **LLM integration:** Spawned `claude` CLI subprocesses inheriting the user's local Claude Code auth — no API key handling on our side
- **Persistence:** SQLite via SQLAlchemy (simple, file-based, easy to demo)
- **Auth:** Local username/password (bcrypt) + JWT session cookies

The plan is split into **6 milestones**, each ending in a demoable artifact. Issues are sized to be ~0.5–2 days of work and include explicit acceptance tests.

---

## Architecture Overview

```
┌──────────────┐    HTTPS/WS    ┌──────────────┐    subprocess    ┌────────────┐
│  React SPA   │ ─────────────► │   FastAPI    │ ───────────────► │ claude CLI │
│ (Vite + TS)  │ ◄───────────── │   + SQLite   │ ◄─────────────── │ (your auth)│
└──────────────┘   stream/SSE   └──────────────┘   stdout stream  └────────────┘
```

Key design decisions:
- **Claude Code integration** uses `claude -p "<prompt>" --output-format stream-json` per turn, with conversation continuity provided via `--resume <session_id>` (Claude Code's own session file) **or** by replaying our stored history into stdin. We pick *per-session subprocess* model: each chat session maps 1:1 to a Claude Code session id. This guarantees true isolation and parallel-safe sessions.
- **Streaming** to the browser uses **Server-Sent Events (SSE)** — simpler than WebSockets and one-way is all we need.
- **Session isolation** is enforced both at the DB layer (foreign keys on `user_id` + `session_id`) and at the process layer (one Claude subprocess per active stream).

---

# Milestone 1: Project Skeleton & Auth

**Goal:** Stand up the repo, both apps, and a working signup/login flow.

**Demoable result:** A reviewer can open the app, see a Login page, click "Sign up", create an account, log in, and land on an empty placeholder home page that says "Hello, <username>". Logging out returns them to the login page. Unauthenticated visits to `/` redirect to `/login`.

## Issues

### Issue 1.1 — Repo scaffolding & dev tooling
**Description:** Create monorepo layout with `frontend/` (Vite + React + TS + Tailwind) and `backend/` (FastAPI + uvicorn + SQLAlchemy + Alembic + pytest). Add root `Makefile` / `npm` scripts that start both. Configure CORS for `localhost:5173 → :8000`. Add `.env.example`, `.gitignore`, Prettier + ESLint, Ruff + Black.
**Expected output:** `make dev` (or `npm run dev`) starts both servers; visiting `localhost:5173` shows Vite default page; `GET localhost:8000/health` returns `{"ok": true}`.
**Dependencies:** none.
**Acceptance tests:**
- `pytest` runs and passes a trivial `test_health` test against the FastAPI app via `TestClient`.
- `npm test` runs and passes a trivial Vitest sanity test.
- Lint and format commands exit 0 on the freshly generated code.

### Issue 1.2 — User model, DB, and migrations
**Description:** Define `User(id, email, username, password_hash, created_at)` SQLAlchemy model. Set up SQLite at `backend/data/app.db`. Add Alembic and create the initial migration. Add a `db.py` session/dep helper.
**Expected output:** Running `alembic upgrade head` creates a `users` table; a `get_db()` FastAPI dependency yields a session.
**Dependencies:** 1.1.
**Acceptance tests:**
- Unit test: create a User, commit, query back by email — equality holds.
- Unique-constraint test: inserting two users with the same email raises `IntegrityError`.

### Issue 1.3 — Signup & login API
**Description:** Implement `POST /auth/signup` (email, username, password → 201 + JWT cookie) and `POST /auth/login` (credentials → 200 + JWT cookie). Use `passlib[bcrypt]` for hashing and `python-jose` for JWTs. Cookie is `HttpOnly`, `SameSite=Lax`. Add `POST /auth/logout` (clears cookie) and `GET /auth/me`. Add a `current_user` FastAPI dependency that 401s if no/invalid token.
**Expected output:** Endpoints behave per spec; protected dep works.
**Dependencies:** 1.2.
**Acceptance tests:**
- Signup with valid payload → 201, `auth_token` cookie set, `/auth/me` returns the user.
- Signup with duplicate email → 409.
- Login with wrong password → 401.
- `/auth/me` without cookie → 401.
- Password is stored hashed (test asserts stored value != plaintext and `bcrypt.verify` succeeds).

### Issue 1.4 — Login & Signup pages (frontend)
**Description:** Build `/login` and `/signup` pages with React Router. Form validation (email format, password ≥ 8 chars). On success store no token in JS (cookie is HttpOnly) but call `/auth/me` to populate an `AuthContext`. Add a `RequireAuth` route wrapper that redirects to `/login`. Style with rounded-rectangle buttons per spec.
**Expected output:** Working pages; auth state survives reload via `/auth/me`; protected `/` redirects when logged out.
**Dependencies:** 1.3.
**Acceptance tests:**
- Vitest + React Testing Library: signup form shows validation errors for empty fields and bad email.
- Mocked-fetch test: successful login navigates to `/`.
- `RequireAuth` test: unauthenticated render redirects to `/login`.

### Issue 1.5 — Auth E2E smoke
**Description:** Add one Playwright test covering signup → logout → login → land on `/`.
**Expected output:** `npx playwright test` is green in CI/local.
**Dependencies:** 1.4.
**Acceptance tests:** the Playwright spec itself.

---

# Milestone 2: Sessions CRUD & Sidebar UI

**Goal:** Users can create, list, rename, and delete chat sessions. The collapsible sidebar is in place. No actual chatting yet — sessions are empty containers.

**Demoable result:** After login, the user sees a sidebar (expanded by default) with a "+ New session" button and a collapse button at the top, plus a list of their sessions. They can create sessions, rename via inline edit, delete with confirmation, click one to "open" it (URL changes to `/c/:id`), and collapse the sidebar to maximize the (still-empty) chat area.

## Issues

### Issue 2.1 — Session & Message data model
**Description:** Add `Session(id, user_id FK, title, claude_session_id NULLABLE, system_prompt NULLABLE, created_at, updated_at)` and `Message(id, session_id FK, role enum['user','assistant'], content TEXT, created_at)`. Indexes on `session_id`, `(user_id, updated_at DESC)`. Alembic migration.
**Expected output:** Migration applies cleanly; cascading delete works (deleting a session removes its messages).
**Dependencies:** 1.2.
**Acceptance tests:**
- Cascade-delete test.
- Cross-user isolation test: User A cannot read User B's session via ORM-level query helpers.

### Issue 2.2 — Sessions REST API
**Description:** Implement:
- `GET /sessions` → list current user's sessions (ordered by `updated_at DESC`)
- `POST /sessions` → create empty session (auto title `"New chat"`)
- `PATCH /sessions/:id` → rename / update system prompt
- `DELETE /sessions/:id` → delete
- `GET /sessions/:id` → session + messages
All endpoints enforce `session.user_id == current_user.id`, returning 404 on mismatch (not 403, to avoid leaking existence).
**Expected output:** Endpoints function and are user-scoped.
**Dependencies:** 1.3, 2.1.
**Acceptance tests:**
- Each endpoint returns 401 unauthenticated.
- User B gets 404 fetching User A's session.
- DELETE actually removes session + messages.
- PATCH rename persists.

### Issue 2.3 — Sidebar component
**Description:** Build `Sidebar.tsx` with:
- Collapse button (icon: `panel-left-close` from lucide-react) at top-left
- New-session button (icon: `square-pen`) at top-right of the sidebar header
- Scrollable session list; each row shows title + "..." menu (rename/delete)
- Rounded-rectangle styling, hover states, active-session highlight
- Default state: **expanded**; collapse persists in `localStorage`
- When collapsed, show a thin rail with just an "expand" icon and "+ new"
**Expected output:** Pixel-clean sidebar matching modern chatbot apps (think Claude.ai layout).
**Dependencies:** 2.2.
**Acceptance tests:**
- RTL test: clicking collapse toggles a `data-collapsed` attribute and `localStorage` key.
- RTL test: clicking "+" calls `POST /sessions` (mocked) and navigates to `/c/:id`.
- RTL test: rename inline-edit fires `PATCH` with new title.
- RTL test: delete shows confirm dialog before firing `DELETE`.

### Issue 2.4 — App shell & routing
**Description:** Build `AppShell` that hosts `Sidebar` + `Outlet`. Routes: `/` (no session selected → empty state placeholder), `/c/:sessionId` (session view placeholder). Wire `RequireAuth` around the shell. Show user menu (avatar + logout) bottom-left of sidebar.
**Expected output:** Navigation between sessions works without full page reload.
**Dependencies:** 1.4, 2.3.
**Acceptance tests:**
- RTL test: clicking a session row updates URL to `/c/:id`.
- RTL test: logout clears auth and redirects to `/login`.

---

# Milestone 3: Claude Code Integration & Single-Session Chat

**Goal:** Send a message in one session and stream back a real Claude Code response, persisted to the DB. Cover the empty-state → active-chat layout transition.

**Demoable result:** Open a fresh session: input bar centered on the page with 4 floating example-prompt bubbles above it. Click a bubble or type a question, hit send: the layout transitions — input slides to the bottom, the user's message appears as a bubble, and Claude's response streams in below as a Markdown-rendered block (no bubble). Reloading the page restores the conversation.

## Issues

### Issue 3.1 — Claude Code subprocess wrapper
**Description:** Build `backend/claude_runner.py` that wraps the `claude` CLI. Two methods:
- `start_session(system_prompt: str | None) -> claude_session_id` — runs `claude --print "<noop init>" --output-format json [--append-system-prompt ...]`, parses returned `session_id`.
- `send_message(claude_session_id, prompt) -> AsyncIterator[StreamEvent]` — runs `claude -p "<prompt>" --resume <id> --output-format stream-json --verbose` and yields parsed JSON events (`text_delta`, `message_done`, `error`).
Use `asyncio.subprocess`. Ensure stderr is captured and surfaced as an `error` event. Hard timeout (configurable, default 180s).
**Expected output:** A standalone script `python -m backend.claude_runner "hello"` prints streamed text.
**Dependencies:** 1.1; the developer machine must be logged into Claude Code (documented in README).
**Acceptance tests:**
- Unit test with the subprocess **mocked** (don't hit the real CLI in CI): assert correct argv is constructed for both `start_session` and `send_message`, including system-prompt passthrough and `--resume`.
- Unit test: malformed JSON line in stream is logged and skipped, not crashing the iterator.
- Unit test: timeout kills the process and yields a final `error` event.
- Manual/local-only test: a real `claude` invocation returns nonempty text.

### Issue 3.2 — Chat send endpoint with SSE streaming
**Description:** `POST /sessions/:id/messages` accepts `{content: string}`:
1. Validates ownership.
2. Persists the user `Message`.
3. If `session.claude_session_id is None`, calls `start_session(...)` and stores the id.
4. Returns an SSE response that pipes `claude_runner.send_message(...)` events to the client as `event: delta`, `event: done`, `event: error`. On `done`, persist the assembled assistant `Message`. Auto-update session `title` from the first user message (truncate to ~60 chars) and `updated_at`.
**Expected output:** A `curl -N` against this endpoint streams text chunks live.
**Dependencies:** 2.2, 3.1.
**Acceptance tests:**
- Integration test (with mocked runner) asserts: user message persisted before stream starts; assistant message persisted on `done`; SSE event sequence is `delta* done`.
- Test: non-owner user → 404.
- Test: if runner emits `error`, an SSE `error` event is sent and **no** assistant message is persisted (or is persisted with an `[error]` marker — pick one and document it).
- Test: `claude_session_id` is set after first call and reused on second call.

### Issue 3.3 — Empty-state chat layout
**Description:** Build `EmptyChatView`: vertically centered input bar, 4 hardcoded example prompt bubbles above it (e.g. "Explain quicksort", "Write a haiku about React", "Debug this stacktrace…", "Brainstorm startup names"). Clicking a bubble fills the input. Rounded-rectangle styling.
**Expected output:** Polished centered hero state.
**Dependencies:** 2.4.
**Acceptance tests:**
- RTL test: clicking a suggestion bubble populates the input.
- Visual snapshot or DOM assertion that input is centered (`data-state="empty"` on container).

### Issue 3.4 — Active chat layout & transition
**Description:** Build `ActiveChatView` with input pinned to bottom, scrollable message list above. Render user messages as right-aligned rounded bubbles; assistant messages as full-width, larger-typography Markdown blocks (no bubble background). Implement transition: when `messages.length` goes from 0 → 1, animate input from center → bottom (CSS transform + `framer-motion` or simple Tailwind transition). Auto-scroll to bottom on new content.
**Expected output:** Smooth visual transition; correct visual differentiation of user vs. assistant.
**Dependencies:** 3.3.
**Acceptance tests:**
- RTL test: container `data-state` flips from `empty` to `active` after first message.
- RTL test: user message is rendered with role=`user` styling class; assistant with role=`assistant`.
- RTL test: auto-scroll triggers when streaming new content (mock `scrollIntoView`).

### Issue 3.5 — Markdown renderer for assistant messages
**Description:** Use `react-markdown` + `remark-gfm` + `rehype-highlight` (or `shiki`) for code blocks. Sanitize via `rehype-sanitize` to prevent XSS from model output. Style: readable line-height, code blocks with copy-button, tables, lists.
**Expected output:** Assistant Markdown renders cleanly with syntax-highlighted code.
**Dependencies:** 3.4.
**Acceptance tests:**
- Unit test: rendering a string with `<script>` tag results in escaped/stripped output (no actual `<script>` node in DOM).
- Unit test: triple-backtick code block renders a `<pre><code>` with the language class.
- Unit test: GFM table renders as `<table>`.

### Issue 3.6 — Frontend SSE client + send/receive wiring
**Description:** Implement `useChatStream(sessionId)` hook using `fetch` + `ReadableStream` (not `EventSource`, since we need cookies + POST). Manages an in-flight assistant message buffer that updates on each delta and finalizes on `done`. Refetch the session's persisted messages on mount.
**Expected output:** End-to-end: type → stream renders live → reload preserves history.
**Dependencies:** 3.2, 3.4, 3.5.
**Acceptance tests:**
- Hook test with mocked `fetch` returning a fake SSE byte stream: state evolves through deltas and finalizes on `done`.
- Hook test: `error` event sets an error state and stops streaming.
- Hook test: unmounting mid-stream aborts the underlying request.

---

# Milestone 4: Multi-Session Isolation & Parallel Chats

**Goal:** Multiple sessions truly behave independently and can stream in parallel without crosstalk. This is a correctness milestone with a strong demo.

**Demoable result:** Open two sessions in two browser tabs. Send a question in each within ~1 second of each other. Both stream concurrently; each reply lands in the correct session. Reload either tab — only that session's history shows. Switching sessions in a single tab never shows the wrong history mid-stream.

## Issues

### Issue 4.1 — Per-session subprocess concurrency model
**Description:** Ensure two simultaneous `POST /sessions/:a/messages` and `POST /sessions/:b/messages` spawn independent `claude` processes and stream back without blocking each other. Verify FastAPI is running with an async worker (uvicorn) and that `claude_runner.send_message` does not hold any global lock. Add per-session in-process lock to **prevent** two concurrent sends to the *same* session (return 409 if one is in flight).
**Expected output:** Concurrent sends to different sessions work; concurrent sends to the same session are rejected cleanly.
**Dependencies:** 3.2.
**Acceptance tests:**
- Async integration test (mocked runner with `asyncio.sleep`): two parallel requests to two sessions both finish in ≈ max(t1, t2), not t1+t2.
- Test: second concurrent request to the *same* session returns 409.
- Test: assistant message from session A is **not** written to session B (assert by DB inspection after parallel run).

### Issue 4.2 — Frontend session-state isolation
**Description:** Refactor chat state into a per-session store (Zustand slice keyed by sessionId, or a React context per route). Switching sessions must not leak in-flight streams or message buffers. Aborting a stream when navigating away.
**Expected output:** No state crosstalk between sessions in the UI.
**Dependencies:** 3.6, 4.1.
**Acceptance tests:**
- RTL test: render session A, start a stream, navigate to session B mid-stream → A's abort controller is called; B shows B's history only.
- RTL test: navigating back to A shows A's persisted final message (refetched from server).

### Issue 4.3 — Sidebar live updates
**Description:** When a message is sent in any session, that session's title (if still "New chat") and `updated_at` should update in the sidebar without a manual refresh. Implement via optimistic local update + invalidation of the sessions list query (TanStack Query).
**Expected output:** Sidebar reorders / retitles in real time.
**Dependencies:** 4.2.
**Acceptance tests:**
- RTL test: after first user message, sidebar entry's title changes from "New chat" to a derived title.
- RTL test: a session that just received a message floats to the top of the list.

---

# Milestone 5: Search & Settings

**Goal:** Make the app feel complete — searching old chats and customizing behavior/theme.

**Demoable result:** Click the search bar above the session list, type a phrase that appears in an old conversation; matching sessions show with the matched snippet highlighted. Click one to jump to that session. Open Settings: toggle dark/light theme (instant change), edit the system prompt for the active session, save, send a new message — Claude's behavior reflects the new system prompt.

## Issues

### Issue 5.1 — Search backend
**Description:** `GET /search?q=...` returns sessions belonging to the current user where `q` matches any message content (case-insensitive substring) or session title. Response includes `[{session_id, title, snippet, matched_role}]`. Use SQLite `LIKE` for v1; design with a comment noting future FTS5 upgrade. Limit to 50 results.
**Expected output:** Endpoint returns relevant sessions with snippets.
**Dependencies:** 2.2, 3.2.
**Acceptance tests:**
- Test: matches in user messages and assistant messages both surface.
- Test: cross-user isolation — User A's search never returns User B's sessions.
- Test: empty `q` returns 400.
- Test: snippet contains the matched substring with ~30 chars context on each side.

### Issue 5.2 — Search UI
**Description:** Add a search input above the session list in the sidebar. Debounced (250ms) calls to `/search`. While searching, replace the session list with results; show snippet with `<mark>` highlighting. Esc or clearing the input restores normal session list.
**Expected output:** Snappy, intuitive search.
**Dependencies:** 5.1, 2.3.
**Acceptance tests:**
- RTL test: typing triggers debounced fetch (use fake timers).
- RTL test: clicking a result navigates to that session.
- RTL test: clearing input restores the full session list.

### Issue 5.3 — Settings storage (backend)
**Description:** Add `UserSettings(user_id PK/FK, theme enum['light','dark','system'], default_system_prompt TEXT)`. Endpoints: `GET /settings`, `PATCH /settings`. The per-session `system_prompt` (already on `Session`) takes precedence over `default_system_prompt`.
**Expected output:** Settings persist and are applied.
**Dependencies:** 1.2.
**Acceptance tests:**
- Test: PATCH then GET round-trips values.
- Test: `claude_runner.start_session` is invoked with the effective system prompt (per-session override > user default > none) — verify via mocked runner.

### Issue 5.4 — Settings UI
**Description:** Settings modal accessible from sidebar footer. Two tabs:
- **Appearance:** light / dark / system radio. Applies via `data-theme` on `<html>` and CSS variables; persist via `PATCH /settings`.
- **Chat behavior:** textarea for default system prompt + a "Edit for current session" toggle that maps to the active session's `system_prompt` (via `PATCH /sessions/:id`).
Save button is rounded-rectangle styled.
**Expected output:** Theme toggles instantly; system prompt changes take effect on the **next** message (note: existing Claude session is not retroactively re-prompted; document this).
**Dependencies:** 5.3, 2.2.
**Acceptance tests:**
- RTL test: changing theme updates `documentElement.dataset.theme`.
- RTL test: saving a per-session prompt fires `PATCH /sessions/:id` with the new value.
- Note in test: changing system prompt resets the session's `claude_session_id` to `NULL` so the next send re-initializes Claude — assert this behavior in an integration test.

---

# Milestone 6: Hardening — Errors, Security, Polish, Tests

**Goal:** Ship-ready quality: graceful errors, security review, accessibility, full test pass.

**Demoable result:** Walk through the app showing: (a) killing the backend mid-stream produces a clean inline error with a "Retry" button rather than a frozen UI; (b) trying to access another user's session via URL fails cleanly; (c) a malicious prompt response containing `<script>` does not execute; (d) keyboard-only navigation works through sidebar, input, and settings; (e) `pytest` and `npm test` and Playwright all green.

## Issues

### Issue 6.1 — Error handling end-to-end
**Description:** Standardize backend error response shape `{error: {code, message}}`. Map exceptions in a FastAPI exception handler. Frontend: show inline error toasts (rounded-rect style) for non-stream errors; inline error block + Retry button inside the chat for stream errors. Network drop during stream → reconnect attempt once, then give up cleanly.
**Expected output:** No silent failures; user always sees something actionable.
**Dependencies:** all M3 issues.
**Acceptance tests:**
- Integration test: forcing a 500 in the message endpoint produces a structured error response and the frontend shows the toast (RTL).
- Hook test: stream that ends with `error` event renders an inline error + Retry that re-POSTs.

### Issue 6.2 — Security review issue
**Description:** Address baseline web-app security:
- HttpOnly + SameSite=Lax cookies; `Secure` in production.
- CSRF: since we use cookies, add a double-submit CSRF token on state-changing endpoints, OR move to `Authorization: Bearer` with token in memory. Pick one and implement.
- Rate-limit `/auth/login` and `/auth/signup` (e.g. `slowapi`, 10/min/IP).
- Validate all path params; ensure ownership checks on every session/message route.
- Sanitize Markdown rendering (already done in 3.5; add an explicit test here).
- Subprocess argv: never interpolate user content into shell strings — always pass via argv list to `asyncio.create_subprocess_exec` (assert in code review).
- Set `Content-Security-Policy` header restricting scripts to self.
**Expected output:** A short `SECURITY.md` describing each control + tests below.
**Dependencies:** 1.3, 3.1, 3.2, 3.5.
**Acceptance tests:**
- Test: login endpoint returns 429 after N rapid calls.
- Test: a session-modifying request without CSRF token is rejected (if CSRF route chosen).
- Test: assistant content `<img src=x onerror=alert(1)>` renders without an `onerror` attribute in the DOM.
- Test: `claude_runner` is invoked with argv list (no `shell=True`).

### Issue 6.3 — Accessibility & keyboard
**Description:** All buttons have `aria-label`; sidebar collapse/new/search reachable by Tab; focus ring visible on rounded-rect buttons; modals trap focus and close on Esc; color contrast ≥ AA in both themes.
**Expected output:** Lighthouse a11y score ≥ 95.
**Dependencies:** 5.4.
**Acceptance tests:**
- Automated axe-core check via `@axe-core/playwright` on `/`, `/login`, settings modal — zero serious violations.
- Playwright test: full flow (login → new session → send → open settings) using only keyboard.

### Issue 6.4 — Full E2E flow test
**Description:** Single Playwright test that signs up a fresh user, creates two sessions, sends a (stubbed) message in each in parallel using a backend `--mock-claude` flag that swaps the runner with a deterministic echo, asserts both replies land in the right session, searches for content, opens settings, switches theme.
**Expected output:** One green spec covering the headline demo.
**Dependencies:** all prior milestones.
**Acceptance tests:** the spec itself; runs in CI.

### Issue 6.5 — README & demo script
**Description:** Write `README.md` covering: prerequisites (Node, Python, an active `claude` CLI login), `make dev`, where to find logs, the `--mock-claude` flag for testing, and a "Demo script" section listing the exact click-path used for stakeholder demos.
**Expected output:** A teammate can clone, install, and run the app within 10 minutes.
**Dependencies:** none functional; do last.
**Acceptance tests:** manual — a teammate (or you on a fresh clone) runs the README steps end to end.

---

## Cross-cutting Notes

- **Why per-session subprocess (not a long-lived daemon):** `claude` CLI's `--resume <session_id>` makes restart-per-turn cheap and gives us hard isolation. A long-lived process per session would require pty management and would complicate parallelism. We can revisit if latency becomes an issue.
- **Why SSE not WebSocket:** one-way streaming is enough; SSE works through proxies and reuses HTTP auth cookies trivially.
- **Why SQLite:** zero-ops for a single-user/team app; swap to Postgres later by changing the SQLAlchemy URL.
- **Out of scope (intentionally deferred):** file/image uploads, tool-use display, multi-tenant org features, mobile-specific layout, OAuth login, conversation export.

---

## Tasks

- [ ] **M1 — Project Skeleton & Auth**
  - [ ] 1.1 Repo scaffolding & dev tooling
  - [ ] 1.2 User model, DB, and migrations
  - [ ] 1.3 Signup & login API
  - [ ] 1.4 Login & Signup pages (frontend)
  - [ ] 1.5 Auth E2E smoke
- [ ] **M2 — Sessions CRUD & Sidebar UI**
  - [ ] 2.1 Session & Message data model
  - [ ] 2.2 Sessions REST API
  - [ ] 2.3 Sidebar component
  - [ ] 2.4 App shell & routing
- [ ] **M3 — Claude Code Integration & Single-Session Chat**
  - [ ] 3.1 Claude Code subprocess wrapper
  - [ ] 3.2 Chat send endpoint with SSE streaming
  - [ ] 3.3 Empty-state chat layout
  - [ ] 3.4 Active chat layout & transition
  - [ ] 3.5 Markdown renderer for assistant messages
  - [ ] 3.6 Frontend SSE client + send/receive wiring
- [ ] **M4 — Multi-Session Isolation & Parallel Chats**
  - [ ] 4.1 Per-session subprocess concurrency model
  - [ ] 4.2 Frontend session-state isolation
  - [ ] 4.3 Sidebar live updates
- [ ] **M5 — Search & Settings**
  - [ ] 5.1 Search backend
  - [ ] 5.2 Search UI
  - [ ] 5.3 Settings storage (backend)
  - [ ] 5.4 Settings UI
- [ ] **M6 — Hardening**
  - [ ] 6.1 Error handling end-to-end
  - [ ] 6.2 Security review issue
  - [ ] 6.3 Accessibility & keyboard
  - [ ] 6.4 Full E2E flow test
  - [ ] 6.5 README & demo script
