.PHONY: tests build run migrate linting unittests

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

unittests:
	uv run coverage run -m pytest --durations=0 tests
	uv run coverage html

tests: linting unittests

open_coverage:
	open 'htmlcov/index.html'
