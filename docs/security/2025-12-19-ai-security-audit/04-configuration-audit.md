# Configuration & Headers Security Audit

## Overview

This document covers the security configuration of the deployed Bookmarks application, including HTTP headers, CORS policy, and TLS configuration.

## Deployed Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| API | https://bookmarks-api.up.railway.app | REST API backend |
| Frontend | https://bookmarks-app.up.railway.app | React SPA |
| MCP | https://bookmarks-mcp.up.railway.app | MCP server |

## HTTP Security Headers Audit

### API Server Headers

**Test Command:**
```bash
curl -sI https://bookmarks-api.up.railway.app/health
```

**Response Headers:**
```http
HTTP/2 200
content-type: application/json
date: Fri, 19 Dec 2025 20:25:22 GMT
server: railway-edge
```

| Header | Present | Value | Recommendation |
|--------|---------|-------|----------------|
| `Strict-Transport-Security` | NO | - | Add: `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | NO | - | Add: `nosniff` |
| `X-Frame-Options` | NO | - | Add: `DENY` (API shouldn't be framed) |
| `Content-Security-Policy` | NO | - | Consider for API responses |
| `X-XSS-Protection` | NO | - | Deprecated, not needed |

### Frontend Headers

**Response Headers:**
```http
HTTP/2 200
content-type: text/html; charset=utf-8
x-content-type-options: nosniff
server: railway-edge
```

| Header | Present | Value | Recommendation |
|--------|---------|-------|----------------|
| `Strict-Transport-Security` | NO | - | Add: `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | YES | `nosniff` | Good |
| `X-Frame-Options` | NO | - | Add: `DENY` |
| `Content-Security-Policy` | NO | - | Add restrictive CSP |
| `Referrer-Policy` | NO | - | Add: `strict-origin-when-cross-origin` |
| `Permissions-Policy` | NO | - | Add to disable unused features |

### Recommended Security Headers

**For API (FastAPI middleware):**

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

**For Frontend (Railway static config or nginx):**

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://bookmarks-api.up.railway.app https://*.auth0.com;
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

---

## CORS Configuration Audit

### Current Configuration

**Source:** `backend/src/api/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### CORS Testing Results

**Test 1: Malicious Origin (Blocked)**
```bash
$ curl -X OPTIONS -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST" \
  https://bookmarks-api.up.railway.app/bookmarks/

HTTP/2 400
Disallowed CORS origin
```

**Result:** PASS - Malicious origin rejected

**Test 2: Legitimate Origin (Allowed)**
```bash
$ curl -X OPTIONS -H "Origin: https://bookmarks-app.up.railway.app" \
  -H "Access-Control-Request-Method: POST" \
  https://bookmarks-api.up.railway.app/bookmarks/

HTTP/2 200
access-control-allow-credentials: true
access-control-allow-origin: https://bookmarks-app.up.railway.app
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
```

**Result:** PASS - Legitimate origin allowed with correct headers

### CORS Security Status

| Check | Status | Notes |
|-------|--------|-------|
| Origin whitelist | PASS | Only configured origins allowed |
| Credentials support | PASS | Properly configured for Auth0 |
| Methods restriction | INFO | Uses wildcard, could be tightened |
| Headers restriction | INFO | Uses wildcard, could be tightened |
| Preflight caching | PASS | 600s max-age |

---

## TLS Configuration

The application is deployed on Railway, which handles TLS termination:

| Check | Status | Notes |
|-------|--------|-------|
| HTTPS only | PASS | Railway enforces HTTPS |
| TLS version | PASS | Railway uses modern TLS |
| Certificate validity | PASS | Railway manages certs |
| HSTS | MISSING | Should be added at app level |

---

## Authentication Configuration

### DEV_MODE Status (Production)

**Test:**
```bash
$ curl -s https://bookmarks-api.up.railway.app/users/me
{"detail":"Not authenticated"}
```

**Result:** PASS - Authentication is enforced

### Auth0 Configuration

| Setting | Environment Variable | Security Note |
|---------|---------------------|---------------|
| Domain | `VITE_AUTH0_DOMAIN` | Public, OK to expose |
| Audience | `VITE_AUTH0_AUDIENCE` | Public, OK to expose |
| Client ID | `VITE_AUTH0_CLIENT_ID` | Public SPA client, OK |
| DEV_MODE | `VITE_DEV_MODE` | Must be `false` in production |

---

## Cookie Security

The application uses Bearer token authentication (no cookies for auth), so cookie security is less critical. However, any cookies set should include:

| Attribute | Recommended Value |
|-----------|-------------------|
| `Secure` | `true` (HTTPS only) |
| `HttpOnly` | `true` (no JS access) |
| `SameSite` | `Strict` or `Lax` |

---

## Environment Variable Security

### Sensitive Variables

| Variable | Contains | Protection |
|----------|----------|------------|
| `DATABASE_URL` | DB credentials | Railway secrets |
| `VITE_DEV_MODE` | Auth bypass flag | Must be false/unset |

### Recommendations

1. **Audit environment variables** - Ensure no secrets in logs
2. **Use Railway secrets** - All sensitive values in encrypted storage
3. **Separate environments** - Different credentials for staging/production

---

## Summary

### Security Posture

| Category | Rating | Notes |
|----------|--------|-------|
| CORS | GOOD | Origin restriction works correctly |
| TLS | GOOD | Railway handles termination |
| Auth Config | GOOD | DEV_MODE disabled in production |
| Security Headers | NEEDS IMPROVEMENT | Missing HSTS, CSP, X-Frame-Options |
| Cookie Security | N/A | Bearer auth, no auth cookies |

### Priority Actions

1. **HIGH**: Add security headers middleware to API
2. **MEDIUM**: Add CSP to frontend
3. **MEDIUM**: Add HSTS header
4. **LOW**: Tighten CORS methods/headers
