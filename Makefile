.PHONY: tests build run migrate linting unit_tests

-include .env
export

####
# Development
####
build:
	uv sync

run:
	uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

####
# Database
####
db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision --autogenerate -m "$(message)"

####
# Testing & Quality
####
linting:
	uv run ruff check src
	uv run ruff check tests

unit_tests:
	uv run coverage run -m pytest --durations=0 tests
	uv run coverage html

integration_tests:

tests_only: unit_tests integration_tests

tests: linting tests_only

open_coverage:
	open 'htmlcov/index.html'
