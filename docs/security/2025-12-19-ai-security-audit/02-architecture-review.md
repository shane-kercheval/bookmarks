# Architecture Security Review

## Overview

This document analyzes the security architecture of the Bookmarks application, covering authentication, authorization, multi-tenancy, and data protection mechanisms.

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Frontend (SPA) │────▶│    API Server   │◀────│   MCP Server    │
│  React + Auth0  │     │     FastAPI     │     │    FastMCP      │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │   PostgreSQL    │
                        │   (Multi-tenant)│
                        └─────────────────┘
```

## Authentication Architecture

### Dual Authentication Paths

The application supports two authentication mechanisms:

| Method | Use Case | Token Format | Validation |
|--------|----------|--------------|------------|
| Auth0 JWT | Web UI | RS256 signed JWT | JWKS verification |
| PAT (Personal Access Token) | CLI/MCP/Scripts | `bm_<random>` | SHA-256 hash comparison |

### Auth0 JWT Flow

1. User authenticates via Auth0 hosted login
2. Auth0 returns RS256-signed JWT
3. Backend verifies JWT using Auth0's JWKS endpoint
4. Claims extracted: `sub` (user ID), `email` (optional)
5. User created/updated in database

**Security Properties:**
- Algorithm enforcement: RS256 only (asymmetric)
- JWKS caching: 1-hour TTL
- Audience and issuer validation enforced
- Automatic user provisioning on first login

### PAT (Personal Access Token) Flow

1. User creates token via web UI
2. Backend generates `bm_<secrets.token_urlsafe(32)>`
3. SHA-256 hash stored in database; plaintext returned once
4. On API request, backend hashes incoming token and compares

**Security Properties:**
- 256 bits of entropy (cryptographically secure)
- Hash-only storage (plaintext never persisted)
- Optional expiration dates
- `last_used_at` tracking for audit

### Token Routing Logic

```python
# backend/src/core/auth.py:156-200
def get_current_user():
    if settings.dev_mode:
        return dev_user  # BYPASS - see Finding #1

    if token.startswith("bm_"):
        return validate_pat(token)
    else:
        return validate_jwt(token)
```

## Multi-Tenancy Architecture

### Database-Level Enforcement

All data tables include `user_id` with foreign key constraints:

| Table | FK Constraint | Cascade Delete |
|-------|---------------|----------------|
| Bookmark | `user_id → users.id` | Yes |
| Tag | `user_id → users.id` | Yes |
| ApiToken | `user_id → users.id` | Yes |
| BookmarkList | `user_id → users.id` | Yes |
| UserSettings | `user_id → users.id` | Yes |

### Query-Level Enforcement

All service layer methods include user_id filtering:

```python
# backend/src/services/bookmark_service.py:262-268
result = await db.execute(
    select(Bookmark).where(
        Bookmark.id == bookmark_id,
        Bookmark.user_id == user_id,  # Always enforced
    )
)
```

**Consistent Pattern Across:**
- `bookmark_service.py` - All CRUD operations
- `token_service.py` - Token management
- `tag_service.py` - Tag operations
- `bookmark_list_service.py` - List management

### Unique Constraints

Tags are scoped to users:
```sql
UniqueConstraint("user_id", "name")  -- Tags unique per user
```

Bookmarks have partial unique index:
```sql
CREATE UNIQUE INDEX uq_bookmark_user_url_active
ON bookmarks (user_id, url)
WHERE deleted_at IS NULL
```

## SSRF Protection

The URL scraping functionality (`/bookmarks/fetch-metadata`) includes SSRF protection:

**Location:** `backend/src/services/url_scraper.py:21-85`

```python
def is_private_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private or
        ip.is_loopback or
        ip.is_link_local or
        ip.is_multicast or
        ip.is_reserved or
        ip.is_unspecified
    )
```

**Protection Layers:**
1. Pre-request validation - Hostname resolved and IP checked
2. Post-redirect validation - Final URL checked after redirects
3. Localhost blocking - Explicit `localhost` check

## Rate Limiting

The metadata fetch endpoint is rate-limited:

**Location:** `backend/src/core/rate_limiter.py`

```python
fetch_metadata_limiter = RateLimiter(
    max_requests=15,
    window_seconds=60
)
```

**Implementation:** Sliding window algorithm, keyed by `user_id`

**Limitation:** In-memory storage; won't work in multi-instance deployments.

## MCP Server Architecture

The MCP server is a separate process that proxies through the REST API:

```
MCP Client ──PAT──▶ MCP Server ──HTTP──▶ API Server ──DB──▶ PostgreSQL
```

**Security Properties:**
- PAT-only authentication (no JWT support)
- All requests proxy through REST API
- Inherits API's multi-tenancy enforcement
- No direct database access

## Session Management

The application uses stateless JWT authentication:

- No server-side session storage
- Token expiration handled by Auth0
- No session fixation risk (no sessions)
- No CSRF tokens needed (Bearer auth)

## Cryptographic Standards

| Purpose | Algorithm | Implementation |
|---------|-----------|----------------|
| JWT Signing | RS256 | Auth0 managed |
| PAT Generation | `secrets.token_urlsafe(32)` | Python stdlib |
| PAT Storage | SHA-256 | `hashlib.sha256` |

## Architecture Recommendations

### Strengths

1. **Proper Auth0 Integration** - RS256, JWKS caching, claim validation
2. **Consistent Multi-tenancy** - user_id filtering at service layer
3. **Defense in Depth** - DB constraints + application logic
4. **SSRF Protection** - Both pre-request and post-redirect checks
5. **Stateless Auth** - No session management complexity

### Areas for Improvement

1. **DEV_MODE Guard** - Add production-time check to prevent accidental enablement
2. **Distributed Rate Limiting** - Use Redis for multi-instance deployments
3. **Audit Logging** - Add security event logging
4. **Token Scopes** - Consider adding scope/permission model for PATs
