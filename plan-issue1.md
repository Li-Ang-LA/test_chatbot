# Plan: Issue #1 — Scaffold Monorepo

## Goal / Context

Create the monorepo skeleton with `frontend/` (Vite + React + TS + Tailwind) and `backend/` (FastAPI + uvicorn + SQLAlchemy + Alembic + pytest). Add root-level `Makefile`, `.gitignore`, `.env.example`, and linting/formatting tooling. This is the foundation for all subsequent issues.

## Files to Create or Modify

```
# Root
.gitignore
.env.example
Makefile

# Frontend
frontend/package.json          (via Vite scaffold)
frontend/tsconfig.json         (via Vite scaffold)
frontend/vite.config.ts        (add Tailwind plugin)
frontend/eslint.config.js      (via Vite scaffold, may tweak)
frontend/.prettierrc
frontend/src/App.tsx            (via scaffold, keep default)
frontend/src/App.test.tsx       (new — vitest sanity test)
frontend/vitest.config.ts      (new)
frontend/src/setupTests.ts     (new — vitest setup)

# Backend
backend/pyproject.toml          (new — deps + ruff/black config)
backend/app/__init__.py
backend/app/main.py             (FastAPI app + health endpoint + CORS)
backend/app/config.py           (settings via pydantic-settings)
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/      (empty initially)
backend/tests/__init__.py
backend/tests/test_health.py    (test_health using TestClient)
backend/ruff.toml               (or inline in pyproject.toml)
```

## Implementation Steps

### Step 1: Root `.gitignore`

Create comprehensive `.gitignore` covering:
- Python: `__pycache__/`, `*.pyc`, `.venv/`, `*.egg-info/`, `.ruff_cache/`
- Node: `node_modules/`, `dist/`
- Environment: `.env`, `.env.local`
- IDE: `.idea/`, `.vscode/`, `*.swp`
- OS: `.DS_Store`, `Thumbs.db`
- SQLite: `*.db`
- Research/plan files are NOT ignored (they're part of the project)

### Step 2: Backend setup

1. Create `backend/pyproject.toml` with:
   - `[project]` metadata + dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `alembic`, `pydantic-settings`, `python-dotenv`
   - `[project.optional-dependencies]` dev: `pytest`, `httpx`, `black`, `ruff`
   - `[tool.ruff]` config: line-length=88, select rules
   - `[tool.black]` config: line-length=88
   - `[tool.pytest.ini_options]` config
2. Create venv + install: `python3 -m venv backend/.venv && pip install -e ".[dev]"`
3. Create `backend/app/__init__.py` (empty)
4. Create `backend/app/config.py` — Pydantic `Settings` class reading from `.env`:
   - `DATABASE_URL` default `sqlite:///./data/app.db`
   - `CORS_ORIGINS` default `http://localhost:5173`
   - `SECRET_KEY` default `change-me-in-production`
5. Create `backend/app/main.py`:
   - FastAPI app instance
   - `CORSMiddleware` with origins from config
   - `GET /health` → `{"ok": true}`
6. Init Alembic: `alembic init alembic` (from backend dir), configure `alembic.ini` + `env.py` for SQLAlchemy URL from config
7. Create `backend/tests/__init__.py` (empty)
8. Create `backend/tests/test_health.py`:
   ```python
   from httpx import ASGITransport, AsyncClient
   import pytest
   from app.main import app

   def test_health():
       from starlette.testclient import TestClient
       client = TestClient(app)
       resp = client.get("/health")
       assert resp.status_code == 200
       assert resp.json() == {"ok": True}
   ```

### Step 3: Frontend setup

1. Scaffold: `npm create vite@latest frontend -- --template react-ts` (from repo root)
2. `cd frontend && npm install`
3. Add Tailwind: `npm install -D @tailwindcss/vite tailwindcss`
4. Update `vite.config.ts` to add `tailwindcss()` plugin
5. Replace `frontend/src/index.css` top with `@import "tailwindcss";`
6. Add Prettier: `npm install -D prettier prettier-plugin-tailwindcss`
7. Create `frontend/.prettierrc`:
   ```json
   {
     "semi": true,
     "singleQuote": true,
     "plugins": ["prettier-plugin-tailwindcss"]
   }
   ```
8. Add Vitest: `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`
9. Create `frontend/vitest.config.ts` with jsdom environment
10. Create `frontend/src/App.test.tsx`:
    ```tsx
    import { describe, it, expect } from 'vitest';
    describe('App', () => {
      it('should pass sanity check', () => {
        expect(1 + 1).toBe(2);
      });
    });
    ```
11. Add npm scripts to `package.json`: `"test": "vitest run"`, `"lint": "eslint ."`, `"format": "prettier --write src/"`

### Step 4: Root `.env.example`

```
# Backend
DATABASE_URL=sqlite:///./data/app.db
SECRET_KEY=change-me-in-production
CORS_ORIGINS=http://localhost:5173

# Frontend (Vite prefixed)
VITE_API_URL=http://localhost:8000
```

### Step 5: Root `Makefile`

```makefile
.PHONY: dev dev-frontend dev-backend test lint format install

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

dev:
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

test:
	cd backend && .venv/bin/pytest
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint

format:
	cd backend && .venv/bin/black . && .venv/bin/ruff check --fix .
	cd frontend && npm run format
```

### Step 6: Verify acceptance criteria

1. `make test` — pytest `test_health` passes, vitest sanity passes
2. `make lint` — ruff + eslint exit 0
3. `make format` — black + prettier exit 0
4. `make dev` — both servers start (manual verification)

## Trade-offs / Alternatives

| Decision | Alternative | Why this wins |
|---|---|---|
| Tailwind v4 (`@tailwindcss/vite`) | Tailwind v3 + PostCSS | v4 is simpler setup, no config file needed, CSS-native |
| Ruff + Black separate | Ruff format only | Issue explicitly requests Black; keep both for now |
| `TestClient` (sync) for health test | `AsyncClient` with httpx | Simpler for a trivial test; async tests come later |
| Makefile | npm workspaces / turborepo | Makefile is explicit, no extra tooling, matches issue spec |
| Single `.env` at root | Per-directory `.env` | Simpler; backend reads via `pydantic-settings`, frontend via Vite |

## Tasks

- [x] Step 1: Create root `.gitignore`
- [x] Step 2: Set up backend (pyproject.toml, venv, FastAPI app, health endpoint, Alembic, config, test)
- [x] Step 3: Set up frontend (Vite scaffold, Tailwind, Prettier, Vitest, sanity test)
- [x] Step 4: Create root `.env.example`
- [x] Step 5: Create root `Makefile`
- [x] Step 6: Verify all acceptance criteria pass
