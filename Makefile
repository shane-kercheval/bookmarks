.PHONY: tests build run migrate linting unit_tests

-include .env
export

####
# Development
####
build:  ## Install dependencies
	uv sync

run:  ## Start API server with hot-reload
	uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

####
# Database
####
db-up:  ## Start PostgreSQL container
	docker compose up -d db

db-down:  ## Stop PostgreSQL container
	docker compose down

migrate:  ## Run database migrations
	uv run alembic upgrade head

migration:  ## Create new migration: make migration message="description"
	uv run alembic revision --autogenerate -m "$(message)"

####
# Testing & Quality
####
linting:  ## Run ruff linter
	uv run ruff check src
	uv run ruff check tests

unit_tests:  ## Run unit tests with coverage
	uv run coverage run -m pytest --durations=0 tests
	uv run coverage html

integration_tests:  ## Run integration tests

tests_only: unit_tests integration_tests

tests: linting tests_only  ## Run linting + all tests

open_coverage:  ## Open coverage report in browser
	open 'htmlcov/index.html'
