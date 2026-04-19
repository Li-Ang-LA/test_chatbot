# Claude Code Web Chatbot

A web chatbot UI backed by the `claude` CLI. Monorepo layout:

- `frontend/` — Vite + React + TypeScript + Tailwind
- `backend/` — FastAPI + SQLAlchemy + Alembic (SQLite)

See [`plan.md`](./plan.md) for the milestone-based development plan.

---

## Prerequisites

- **Node** ≥ 20
- **Python** ≥ 3.12
- An active **Claude Code CLI** login on this machine (only needed once chat
  functionality lands in M3; not required for the M1/M2 flows). Run
  `claude login` once. The backend spawns the `claude` binary from your `PATH`;
  set `CLAUDE_CLI_BIN` to override if it lives elsewhere.

---

## Setup

Install backend venv + frontend `node_modules` in one shot:

```bash
make install
```

Copy env template and set `SECRET_KEY`:

```bash
cp .env.example backend/.env
# edit backend/.env — SECRET_KEY must be a random string (≥ 32 bytes recommended)
```

---

## Run the app

Both servers in parallel:

```bash
make dev
```

- Backend → http://localhost:8000 (`/health` returns `{"ok": true}`)
- Frontend → http://localhost:5173

Or individually, in two terminals:

```bash
make dev-backend   # uvicorn app.main:app --reload --port 8000
make dev-frontend  # vite dev server
```

---

## Environment variables

Backend (`backend/.env`):

| Variable        | Default                       | Notes                                             |
| --------------- | ----------------------------- | ------------------------------------------------- |
| `SECRET_KEY`    | _(required)_                  | HMAC key for JWTs. Random string, ≥ 32 bytes.     |
| `DATABASE_URL`  | `sqlite:///./data/app.db`     | SQLAlchemy URL. SQLite file by default.           |
| `CORS_ORIGINS`  | `http://localhost:5173`       | Comma-separated list of allowed origins.          |
| `COOKIE_SECURE` | `false`                       | Set to `true` in production (HTTPS only).         |

Frontend (`frontend/.env`, Vite-prefixed):

| Variable       | Default                 |
| -------------- | ----------------------- |
| `VITE_API_URL` | `http://localhost:8000` |

---

## Tests

### Backend unit tests (pytest)

```bash
cd backend && .venv/bin/pytest
# or
make test   # runs backend + frontend unit suites
```

### Frontend unit tests (Vitest + React Testing Library)

```bash
cd frontend && npm test
```

### End-to-end tests (Playwright)

E2E tests live in `frontend/e2e/`. Playwright's `webServer` config spins up a
fresh backend (against `data/e2e.db`) and the Vite dev server automatically —
you do **not** need to pre-start either.

First-time Chromium browser install:

```bash
cd frontend && npx playwright install chromium
```

Run the suite:

```bash
cd frontend && npm run test:e2e
```

Useful flags:

- `npm run test:e2e -- --headed` — watch the browser drive the UI
- `npm run test:e2e -- --ui` — interactive Playwright UI
- `npm run test:e2e -- --debug` — step through a spec

---

## Lint & format

```bash
make lint     # ruff + eslint
make format   # black + ruff --fix, prettier
```

---

## Manual smoke: Claude Code runner

```bash
cd backend
.venv/bin/python -m app.claude_runner "say hello in one word"
```

Streams the assistant's reply to stdout. Requires an active `claude login` on
this machine; this is the only path that hits the real CLI (unit tests mock
the subprocess).

---

## Database migrations

```bash
cd backend
.venv/bin/alembic upgrade head                          # apply latest
.venv/bin/alembic revision --autogenerate -m "message"  # new migration
```

The default SQLite file lives at `backend/data/app.db`.
