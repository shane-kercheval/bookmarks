.PHONY: tests build run mcp-server migrate backend-lint unit_tests pen_tests frontend-install frontend-build frontend-dev frontend-tests frontend-lint

-include .env
export

# Set PYTHONPATH for backend
PYTHONPATH := backend/src

####
# Backend Development
####
build:  ## Install backend dependencies
	uv sync

run:  ## Start API server with hot-reload
	PYTHONPATH=$(PYTHONPATH) uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

####
# MCP Server
####
mcp-server:  ## Start MCP server (requires API server running on port 8000)
	PYTHONPATH=$(PYTHONPATH) uv run python -m mcp_server

####
# Frontend Development
####
frontend-install:  ## Install frontend dependencies
	cd frontend && npm install

frontend-dev:  ## Start frontend dev server
	cd frontend && npm run dev

frontend-build:  ## Build frontend for production
	cd frontend && npm run build

frontend-lint:  ## Run frontend linter
	cd frontend && npm run lint

frontend-tests:  ## Run frontend tests
	cd frontend && npm run test:run

####
# Database
####
db-up:  ## Start PostgreSQL container
	docker compose up -d db

db-down:  ## Stop PostgreSQL container
	docker compose down

db-restart:  ## Restart PostgreSQL container
	docker compose down && docker compose up -d db

db-rebuild:  ## Rebuild and restart PostgreSQL container
	docker compose down && docker compose up -d --build db

migrate:  ## Run database migrations
	uv run alembic upgrade head

migration:  ## Create new migration: make migration message="description"
	uv run alembic revision --autogenerate -m "$(message)"

####
# Testing & Quality
####
backend-lint:  ## Run ruff linter on backend
	uv run ruff check backend/src
	uv run ruff check backend/tests

backend-tests:  ## Run backend unit tests with coverage
	uv run coverage run -m pytest --durations=20 backend/tests
	uv run coverage html

tests: backend-lint backend-tests frontend-lint frontend-tests ## Run linting + all tests

pen_tests:  ## Run live penetration tests (requires SECURITY_TEST_USER_A_PAT and SECURITY_TEST_USER_B_PAT in .env)
	uv run pytest backend/tests/security/test_live_penetration.py -v

dependency-audit:  ## Run audits to check for vulnerable dependencies
	uv run pip-audit
	npm audit --prefix frontend

security: dependency-audit pen_tests  ## Run security checks

open_coverage:  ## Open coverage report in browser
	open 'htmlcov/index.html'
