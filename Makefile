.PHONY: tests build run mcp-server migrate linting unit_tests frontend-build frontend-dev frontend-test

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

frontend-test:  ## Run frontend tests
	cd frontend && npm run test:run

frontend-lint:  ## Run frontend linter
	cd frontend && npm run lint

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
linting:  ## Run ruff linter on backend
	uv run ruff check backend/src
	uv run ruff check backend/tests

unit_tests:  ## Run backend unit tests with coverage
	uv run coverage run -m pytest --durations=0 backend/tests
	uv run coverage html

integration_tests:  ## Run integration tests

tests_only: unit_tests integration_tests

tests: linting tests_only frontend-test ## Run linting + all tests

open_coverage:  ## Open coverage report in browser
	open 'htmlcov/index.html'
