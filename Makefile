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
