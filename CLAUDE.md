# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bookmark management system with tagging and search capabilities. Multi-tenant architecture with Auth0 authentication (bypassed in DEV_MODE).

## Common Commands

```bash
# Backend
make build              # Install backend dependencies (uv sync)
make run                # Start API server with hot-reload (port 8000)
make linting            # Run ruff linter on backend
make unit_tests         # Run backend tests with coverage
make tests              # Run linting + all tests (backend + frontend)

# Run a single backend test
uv run pytest backend/tests/path/to/test_file.py::test_function_name -v

# Frontend (from frontend/ directory)
npm install             # Install dependencies
npm run dev             # Start dev server (port 5173)
npm run test:run        # Run tests once
npm run test            # Run tests in watch mode
npm run lint            # Run ESLint

# Database
make db-up              # Start PostgreSQL container
make migrate            # Run Alembic migrations
make migration message="description"  # Create new migration
```

## Architecture

### Backend (`backend/src/`)
- **api/**: FastAPI routers and dependencies
  - `main.py`: App entry point, CORS config, router registration
  - `dependencies.py`: Re-exports `get_async_session`, `get_current_user`, `get_settings`
  - `routers/`: Endpoint handlers (bookmarks, users, tags, tokens, health)
- **core/**: Configuration (`config.py`) and authentication (`auth.py`)
- **models/**: SQLAlchemy ORM models (User, Bookmark, ApiToken)
- **schemas/**: Pydantic request/response schemas
- **services/**: Business logic (bookmark_service, token_service, url_scraper)
- **db/**: Database session management and Alembic migrations

### Frontend (`frontend/src/`)
- React 19 + TypeScript + Vite + Tailwind CSS
- **components/**: Reusable UI components
- **pages/**: Route pages
- **hooks/**: Custom React hooks
- **services/**: API client layer
- Auth via `@auth0/auth0-react`

### Key Patterns
- All database tables include `user_id` for multi-tenancy
- Tests use testcontainers for PostgreSQL with transaction rollback isolation
- `DEV_MODE=true` bypasses authentication for local development
- Personal Access Tokens (PATs) prefixed with `bm_` for programmatic API access

## Testing

Backend tests use pytest with async support. The `conftest.py` sets up:
- PostgreSQL container (session-scoped)
- Transaction rollback per test for isolation
- FastAPI test client with session override

Test naming convention: `test__<function_name>__<scenario>`

## Code Style

- Python: ruff for linting, type hints required on all functions
- Use `uv` for package management (not pip)
- Single quotes for code strings, double quotes for user-facing strings
- Docstrings in Google style with Args/Returns/Raises sections
