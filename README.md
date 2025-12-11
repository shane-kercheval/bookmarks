# Bookmarks API

A bookmark management system with tagging and search capabilities.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker (for PostgreSQL)

## Quick Start

```bash
make build                # Install dependencies
cp .env.example .env      # Configure environment (edit with your Auth0 credentials)
make db-up                # Start PostgreSQL
make migrate              # Create database tables
make run                  # Start API at http://localhost:8000
```

To stop: `Ctrl+C` to stop the API, then `make db-down` to stop PostgreSQL.

## Commands

See `Makefile` for all available commands.

## Configuration

See `.env.example` for all environment variables. Key setting:

- `DEV_MODE=true` bypasses auth for local development
- `DEV_MODE=false` requires real Auth0 JWT tokens

## Testing Authentication

With `DEV_MODE=true` (default), auth is bypassed:
```bash
curl http://localhost:8000/users/me
```

To test real Auth0 authentication:

1. Set `DEV_MODE=false` in `.env`
2. Restart the API server (`Ctrl+C`, then `make run`)
3. Get a test token from Auth0: **Applications → APIs → Bookmarks API → Test tab**
4. Test:
```bash
curl http://localhost:8000/users/me \
  -H "Authorization: Bearer <paste-token-here>"
```
