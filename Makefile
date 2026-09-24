# ЖерБақылау — developer commands. Every target has a cross-platform equivalent
# (plain docker / uv / npm commands), listed in CLAUDE.md for Windows without make.

API := apps/api
WEB := apps/web
PY  := uv run --project $(API) python
BASE_URL ?= http://localhost:8000

.DEFAULT_GOAL := help
.PHONY: help setup up up-cloud down logs db dev-api dev-web migrate supabase-sql seed demo-reset \
        demo-reset-remote test test-api test-web lint lint-api lint-web fmt gen-types gen-parcels e2e \
        inspector build-web check

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Install API and web dependencies, create .env if missing
	$(PY) -c "import shutil, pathlib; p = pathlib.Path('.env'); p.exists() or shutil.copy('.env.example', p)"
	cd $(API) && uv sync
	cd $(WEB) && npm ci

up: ## Start PostGIS + Redis + API in Docker (migrations and seed run on start)
	docker compose up -d --build

up-cloud: ## Start Redis + API only (DATABASE_URL_DOCKER points to Supabase)
	docker compose up -d --build --no-deps redis api

down: ## Stop containers
	docker compose down

logs: ## Tail API logs
	docker compose logs -f api

db: ## Start only PostGIS and Redis (for running the API on the host)
	docker compose up -d db redis

dev-api: ## Run the API on the host with hot reload
	cd $(API) && uv run uvicorn app.main:app --reload --port 8000

dev-web: ## Run the web panel (Vite dev server)
	cd $(WEB) && npm run dev

migrate: ## Apply Alembic migrations
	cd $(API) && uv run alembic upgrade head

supabase-sql: ## Apply RLS / realtime / storage SQL (idempotent)
	$(PY) scripts/apply_supabase_sql.py

seed: ## Seed demo data if the database is empty
	$(PY) scripts/seed.py

demo-reset: ## Reset demo data in the database from DATABASE_URL
	$(PY) scripts/demo_reset.py

demo-reset-remote: ## Reset demo data through a deployed API: make demo-reset-remote BASE_URL=https://...
	$(PY) scripts/demo_reset.py --base-url $(BASE_URL)

inspector: ## Create the demo inspector in Supabase Auth
	$(PY) scripts/create_inspector.py

test: test-api test-web ## Run all tests

test-api: ## Backend tests (needs PostGIS: make db)
	cd $(API) && uv run pytest

test-web: ## Frontend type check + unit tests
	cd $(WEB) && npm run typecheck && npm test

lint: lint-api lint-web ## Run all linters

lint-api:
	cd $(API) && uv run ruff check . ../../scripts && uv run ruff format --check . ../../scripts && uv run mypy app

lint-web:
	cd $(WEB) && npm run lint && npm run format:check

fmt: ## Auto-format code
	cd $(API) && uv run ruff check --fix . ../../scripts && uv run ruff format . ../../scripts
	cd $(WEB) && npm run format

gen-types: ## Export OpenAPI and regenerate apps/web/src/api/schema.d.ts
	$(PY) scripts/gen_types.py

gen-parcels: ## Regenerate packages/seed/parcels.geojson
	$(PY) scripts/gen_parcels.py

e2e: ## End-to-end smoke test: make e2e BASE_URL=https://...
	$(PY) scripts/e2e_smoke.py --base-url $(BASE_URL)

build-web: ## Production build of the web panel
	cd $(WEB) && npm run build

check: lint test build-web ## Everything CI runs
