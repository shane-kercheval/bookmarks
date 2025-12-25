.PHONY: tests build run mcp-server migrate backend-lint unit_tests pen_tests frontend-install frontend-build frontend-dev frontend-tests frontend-lint frontend-typecheck docker-up docker-down docker-restart docker-rebuild docker-logs redis-cli

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

frontend-typecheck:  ## Run TypeScript type checking
	cd frontend && npm run typecheck

frontend-tests:  ## Run frontend tests
	cd frontend && npm run test:run

frontend-verify: frontend-lint frontend-typecheck frontend-tests

####
# Docker (PostgreSQL + Redis)
####
docker-up:  ## Start all containers (PostgreSQL + Redis)
	docker compose up -d

docker-down:  ## Stop all containers
	docker compose down

docker-restart:  ## Restart all containers
	docker compose down && docker compose up -d

docker-rebuild:  ## Rebuild and restart all containers
	docker compose down && docker compose up -d --build

docker-logs:  ## Show container logs (follow mode)
	docker compose logs -f

redis-cli:  ## Connect to Redis CLI
	docker compose exec redis redis-cli

####
# Database Migrations
####
migrate:  ## Run database migrations
	uv run alembic upgrade head

migration:  ## Create new migration: make migration message="description"
	uv run alembic revision --autogenerate -m "$(message)"

####
# Testing & Quality
####
backend-lint:  ## Run ruff linter on backend
	uv run ruff check backend/src --fix --unsafe-fixes
	uv run ruff check backend/tests --fix --unsafe-fixes

backend-tests:  ## Run backend unit tests with coverage (excludes live pen tests)
	uv run coverage run -m pytest --durations=20 backend/tests --ignore=backend/tests/security/test_live_penetration.py
	uv run coverage html

backend-verify: backend-lint backend-tests

lint: backend-lint frontend-lint

tests: backend-verify frontend-verify

pen_tests:  ## Run live penetration tests (requires SECURITY_TEST_USER_A_PAT and SECURITY_TEST_USER_B_PAT in .env)
	uv run pytest backend/tests/security/test_live_penetration.py -v

dependency-audit:  ## Run audits to check for vulnerable dependencies
	uv run pip-audit
	npm audit --prefix frontend

security: dependency-audit pen_tests  ## Run security checks

open_coverage:  ## Open coverage report in browser
	open 'htmlcov/index.html'
