# Research: Issue #1 — Scaffold Monorepo

## Current State

- Repo is nearly empty: only `plan.md` and `.claude/` exist
- No `.gitignore`, no `package.json`, no Python project files
- Available toolchain: Node v23.5.0, npm 10.9.2, Python 3.14.0, pip 25.3, GNU Make 3.81
- Platform: macOS (Darwin 25.3.0, Apple Silicon via Homebrew)

## Deliverables (from Issue #1)

1. `frontend/` — Vite + React + TypeScript + Tailwind CSS
2. `backend/` — FastAPI + uvicorn + SQLAlchemy + Alembic + pytest
3. Root `Makefile` — `make dev` starts both servers
4. CORS configured for `localhost:5173 → :8000`
5. `.env.example`, `.gitignore`
6. Linting: Prettier + ESLint (frontend), Ruff + Black (backend)
7. Acceptance: health endpoint, test_health pytest, vitest sanity, lint passes

## Technical Decisions

### Frontend

- **Vite 6.x** — latest stable, `npm create vite@latest frontend -- --template react-ts`
- **Tailwind CSS v4** — current latest; uses `@tailwindcss/vite` plugin, no `tailwind.config.js` needed
- **ESLint** — Vite template includes `eslint.config.js` out of the box
- **Prettier** — add `.prettierrc` with Tailwind plugin
- **Vitest** — already bundled with Vite ecosystem; add `vitest` + `@testing-library/react`
- Dev server default: `localhost:5173`

### Backend

- **Python virtual environment** — `python3 -m venv backend/.venv` to isolate deps
- **FastAPI + uvicorn** — standard async setup
- **SQLAlchemy 2.x** — async style with `mapped_column`
- **Alembic** — for migrations, configured against SQLite
- **Ruff** — replaces flake8/isort, very fast; add `ruff.toml` or section in `pyproject.toml`
- **Black** — formatter (Ruff can also format, but issue explicitly asks for Black)
- **pytest + httpx** — `TestClient` via `httpx.ASGITransport` for async FastAPI testing
- Dev server: `localhost:8000`

### Root

- **Makefile** with targets: `dev` (runs both), `dev-frontend`, `dev-backend`, `lint`, `format`, `test`
- Use `&` to run both servers in parallel from Make, with `trap` for cleanup
- `.env.example` — document `DATABASE_URL`, `CORS_ORIGINS`, `SECRET_KEY`
- `.gitignore` — Node, Python, venv, .env, IDE files, OS files

### CORS

- FastAPI `CORSMiddleware` allowing origin `http://localhost:5173`
- Configured via env var `CORS_ORIGINS` for flexibility

## Risks / Notes

- Python 3.14 is bleeding edge (released April 2025) — some packages may not have wheels yet. Fall back to source build if needed.
- Tailwind v4 has a different setup than v3 — no `tailwind.config.js`, uses CSS-based config with `@import "tailwindcss"`.
- The Makefile `dev` target needs to handle graceful shutdown of both processes (trap SIGINT).
