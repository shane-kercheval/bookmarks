# Bookmarks

A bookmark management system with tagging and search capabilities.

## Features

- **Tag-based organization** - Filter bookmarks by tags with AND/OR matching
- **URL metadata extraction** - Auto-fetch title, description, and page content from URLs
- **Full-text search** - Search across title, description, URL, and content
- **Soft delete & restore** - Delete bookmarks without permanent loss
- **Archive** - Hide bookmarks without deleting them
- **Keyboard shortcuts** - Quick actions for power users
- **Personal Access Tokens** - Programmatic API access for CLI tools and scripts
- **MCP Server** - AI agent access via Model Context Protocol (Claude, etc.)

## Project Structure

```
bookmarks/
├── ai-instructions  # Prompts containing guidelines for AI
├── backend/         # FastAPI backend
├── frontend/        # React frontend
├── docs/            # Contains implementation plans for AI coding agents
├── .env.example     # Environment configuration
└── Makefile         # Development commands
```

## Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (for frontend)
- Docker (for PostgreSQL)

## Quick Start

```bash
# Setup
cp .env.example .env
make build          # Install backend dependencies
make db-up          # Start PostgreSQL
make migrate        # Run database migrations

# Run backend
make run            # API at http://localhost:8000/docs

# Run frontend (separate terminal)
cd frontend && npm install && npm run dev
# Frontend at http://localhost:5173
```

With default `VITE_DEV_MODE=true`, authentication is bypassed for local development.

### Testing with Auth0

To test real authentication:

1. **Set up Auth0** ([auth0.com](https://auth0.com)):
   - Create an account and tenant
   - Create an API (identifier/audience: `https://bookmarks-api`)
   - Create a Single Page Application (note the Client ID)

2. **Configure `.env`**:
   ```bash
   VITE_DEV_MODE=false
   VITE_AUTH0_DOMAIN=your-tenant.auth0.com
   VITE_AUTH0_CLIENT_ID=your-spa-client-id
   VITE_AUTH0_AUDIENCE=https://bookmarks-api
   ```

3. **Test backend** (get a test token from Auth0 Dashboard → APIs → Test tab):
   ```bash
   curl http://localhost:8000/users/me \
     -H "Authorization: Bearer <paste-token-here>"
   ```

4. **Test frontend**: Visit http://localhost:5173 and click "Get Started" to log in.

## Configuration

See `.env.example` for all options. Key settings:

- `VITE_DEV_MODE=true` - Bypasses auth (local dev)
- `VITE_AUTH0_*` - Auth0 config (used by both backend and frontend, empty = dev mode)

## Commands

See `Makefile` for all commands. Run `make` with no args to see help.

## Testing

```bash
make tests          # Run backend linting + tests
make frontend-test  # Run frontend tests
```

## API Documentation

With the backend running: http://localhost:8000/docs

## Personal Access Tokens

PATs allow programmatic API access for CLI tools and scripts.

```bash
# Create a token (with VITE_DEV_MODE=true, no auth header needed)
curl -X POST http://localhost:8000/tokens/ \
  -H "Content-Type: application/json" \
  -d '{"name": "My CLI Token"}'

# Use the token
curl http://localhost:8000/bookmarks/ \
  -H "Authorization: Bearer bm_abc123..."
```

Tokens are stored hashed. The `bm_` prefix distinguishes PATs from Auth0 JWTs.

## MCP Server (AI Agent Access)

The MCP (Model Context Protocol) server allows AI agents like Claude to interact with your bookmarks programmatically.

### Running the MCP Server

```bash
# Requires the main API to be running on port 8000
make mcp-server    # Starts MCP server on port 8001
```

### Available Tools

| Tool | Description |
|------|-------------|
| `search_bookmarks` | Search with text query and tag filtering |
| `get_bookmark` | Get full details of a bookmark by ID |
| `create_bookmark` | Create a new bookmark (auto-fetches metadata) |
| `list_tags` | List all tags with usage counts |

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend API URL |
| `MCP_HOST` | `0.0.0.0` | MCP server bind address |
| `MCP_PORT` | `8001` | MCP server port |

### Testing with MCP Inspector

```bash
# Run MCP Inspector
npx @modelcontextprotocol/inspector

# Connect to: http://localhost:8001/mcp
# Add header: Authorization: Bearer bm_your_token_here
```

### Claude Desktop Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "bookmarks": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:8001/mcp",
        "--header",
        "Authorization: Bearer bm_your_token_here"
      ]
    }
  }
}
```

Replace `bm_your_token_here` with a Personal Access Token created via the API.

## Security

### SSRF Protection

The `/bookmarks/fetch-metadata` endpoint fetches URLs provided by users. To prevent Server-Side Request Forgery (SSRF) attacks, all URLs are validated before fetching:

- **Blocked:** Private IPs (`10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`), loopback (`127.0.0.1`, `::1`), link-local (`169.254.x.x`), and `localhost`
- **DNS resolution check:** Hostnames are resolved to verify they don't point to internal IPs
- **Redirect protection:** Final URLs after redirects are also validated

This prevents attackers from using your server to probe internal networks or cloud metadata endpoints.

**Location:** `backend/src/services/url_scraper.py`

### Rate Limiting

The `/bookmarks/fetch-metadata` endpoint is rate-limited to prevent abuse:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_requests` | 15 | Requests allowed per window |
| `window_seconds` | 60 | Sliding window duration |

Rate limiting is per authenticated user. When exceeded, returns HTTP 429 with `Retry-After` header.

**Location:** `backend/src/core/rate_limiter.py`

To adjust limits, modify the `fetch_metadata_limiter` instance:

```python
fetch_metadata_limiter = RateLimiter(max_requests=15, window_seconds=60)
```

### Content Size Limit

Bookmark content (extracted page text) is limited to **512,000 characters** (~500KB) per bookmark. This prevents storing excessively large pages while accommodating most articles and documentation.

Content exceeding this limit will be rejected with a validation error.

**Location:** `backend/src/schemas/bookmark.py` (`MAX_CONTENT_LENGTH`)
