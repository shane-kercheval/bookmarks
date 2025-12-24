# Testing Gaps: Rate Limiting and Auth Caching

## Overview

Code review of the rate limiting and auth caching implementation revealed that while **unit tests exist and use real Redis via testcontainers**, there are gaps at the **HTTP integration layer** and for **daily limits**.

The components work in isolation, but we lack tests proving the wiring is correct end-to-end.

## Current Coverage

| Layer | Rate Limiting | Auth Caching |
|-------|---------------|--------------|
| Unit tests (real Redis) | ✅ Yes | ✅ Yes |
| HTTP integration (real Redis) | ❌ Mocked | ❌ Missing |
| Daily limits | ❌ Missing | N/A |

## Test Strategy

### Use Testcontainers (Not fakeredis)

The implementation plan states: "fakeredis does NOT accurately support Lua scripts."

Rate limiting uses Lua scripts for atomic operations, so we must use real Redis. The existing `conftest.py` already wires testcontainers Redis to the HTTP client fixture—we just need tests that don't mock over it.

### Proving "Cache Hit Skips DB"

For auth cache tests, we need to prove cache hits avoid database queries. Options:

1. **Spy on `session.execute`** - Wrap to count DB calls
2. **Verify cache entry exists** - Trust code path after confirming cache populated
3. **Timing-based** - Unreliable, avoid

Use option 1 for one definitive test, option 2 for the rest.

---

## Gap 1: Rate Limit HTTP Integration

**Location:** `backend/tests/integration/test_rate_limit_integration.py` (new file)

**Why:** The only existing HTTP test (`test_fetch_metadata_rate_limited`) mocks the rate limiter. No test proves the full flow works with real Redis.

### Tests Needed

| Test | Purpose |
|------|---------|
| Successful request includes `X-RateLimit-*` headers | Middleware wiring works |
| Headers show decreasing `Remaining` count across requests | Real Redis tracking |
| Request exceeding per-minute limit returns 429 | Limit enforcement works |
| 429 response includes `Retry-After` and all rate limit headers | Exception handler works |
| Different auth types (PAT vs Auth0) have different limits | Tier differentiation works |

### Approach

```python
# Make requests and verify headers
response = await client.get("/bookmarks", headers=auth_headers)
assert "X-RateLimit-Limit" in response.headers
assert "X-RateLimit-Remaining" in response.headers
assert "X-RateLimit-Reset" in response.headers

# Verify remaining decreases
remaining_1 = int(response.headers["X-RateLimit-Remaining"])
response_2 = await client.get("/bookmarks", headers=auth_headers)
remaining_2 = int(response_2.headers["X-RateLimit-Remaining"])
assert remaining_2 < remaining_1
```

For limit exceeded test, use a low-limit operation (e.g., SENSITIVE at 30/min) or manipulate Redis directly to simulate near-limit state.

---

## Gap 2: Daily Limit Tests

**Location:** `backend/tests/core/test_rate_limiter.py` (extend existing)

**Why:** Daily limit logic (`rate_limiter.py:128-144`) is completely untested. The fixed window Lua script is tested, but not through the rate limiter's daily limit code path.

### Tests Needed

| Test | Purpose |
|------|---------|
| Daily limit blocks after per-minute passes | Fixed window integration works |
| General vs sensitive have separate daily pools | Pool separation works |
| Daily limit returns correct `reset` timestamp | TTL calculation works |

### Approach

```python
# Exhaust per-minute limit, then exhaust daily limit
# Verify daily limit blocks with longer retry_after (hours, not seconds)
```

---

## Gap 3: Auth Cache HTTP Integration

**Location:** `backend/tests/integration/test_auth_cache_integration.py` (new file)

**Why:** No test verifies that authenticated HTTP requests actually use the cache, or that cache invalidation works through the HTTP layer.

### Tests Needed

| Test | Purpose |
|------|---------|
| After authenticated request, cache entry exists in Redis | Cache population works |
| Second request uses cache (no DB query) | Cache hit path works |
| `POST /consent/me` clears cache entry | Invalidation wiring works |
| Next request after invalidation repopulates cache | Recovery works |
| Cache entry contains correct user and consent data | Data integrity |

### Approach

For "no DB query" proof:

```python
# Option 1: Spy on session.execute
call_count = 0
original_execute = session.execute

async def counting_execute(*args, **kwargs):
    nonlocal call_count
    call_count += 1
    return await original_execute(*args, **kwargs)

# First request: expect DB calls (cache miss)
# Second request: expect zero additional DB calls (cache hit)
```

For cache verification:

```python
# Verify cache entry exists after request
cache_key = f"auth:v1:user:auth0:{auth0_id}"
cached_data = await redis_client.get(cache_key)
assert cached_data is not None

# Verify invalidation clears it
await client.post("/consent/me", json=consent_data, headers=auth_headers)
cached_data = await redis_client.get(cache_key)
assert cached_data is None
```

---

## Gap 4: Redis Fallback at HTTP Layer

**Location:** `backend/tests/integration/test_redis_fallback_integration.py` (new file)

**Why:** Unit tests verify fallback when Redis is disabled/unavailable, but no HTTP test verifies the full request succeeds with degraded functionality.

### Tests Needed

| Test | Purpose |
|------|---------|
| Request succeeds when Redis unavailable | Fail-open works E2E |
| No rate limit headers when Redis unavailable | Graceful degradation |
| Auth works (falls back to DB) when Redis unavailable | Auth fallback works |

### Approach

```python
# Temporarily disable Redis mid-test
set_redis_client(None)

# Request should still succeed
response = await client.get("/bookmarks", headers=auth_headers)
assert response.status_code == 200

# No rate limit headers (or zeros)
assert "X-RateLimit-Remaining" not in response.headers  # or check for 0
```

---

## Gap 5: Edge Cases

**Location:** Extend existing test files

### Script SHA Not Loaded

What if Redis connects but Lua scripts fail to load?

```python
# Connect Redis but clear script SHAs
redis_client._sliding_window_sha = None
# Verify rate limiter fails open
```

### Email Mismatch Cache Fallthrough

When cached email differs from Auth0 email, should fall through to DB.

```python
# Cache user with old email
# Make request with JWT containing new email
# Verify DB was hit and email updated
```

---

## Gap 6: Null Email Handling

**Location:** `backend/tests/core/test_auth.py` (new file) and extend existing fixtures

**Why:** Email is nullable by design (some Auth0 providers don't include it), and the code handles this with `if email and ...` patterns. However, **every test fixture creates users with email**—no test verifies the null email path works.

### Current State

- Model: `email: Mapped[str | None]` (nullable)
- Auth code: Uses `if email and cached.email != email:` pattern
- Tests: All fixtures use `User(auth0_id="...", email="test@example.com")`

### Tests Needed

| Test | Purpose |
|------|---------|
| `get_or_create_user` works with `email=None` | User creation without email |
| Auth cache works with null email user | Cache stores/retrieves null email |
| Full auth flow works when JWT has no email claim | E2E null email path |
| Email update from null to value works | Transition handling |

### Approach

```python
# Create user without email
user = await get_or_create_user(db, auth0_id="auth0|no-email")
assert user.email is None

# Verify cache entry has null email
cached = await auth_cache.get_by_auth0_id("auth0|no-email")
assert cached.email is None

# Later request with email should update
user = await get_or_create_user(db, auth0_id="auth0|no-email", email="new@test.com")
assert user.email == "new@test.com"
```

---

## File Structure

```
backend/tests/
├── integration/                          # NEW directory
│   ├── test_rate_limit_integration.py    # Gap 1
│   ├── test_auth_cache_integration.py    # Gap 3
│   └── test_redis_fallback_integration.py # Gap 5
└── core/
    ├── test_rate_limiter.py              # Gap 2 (extend existing)
    └── test_auth.py                      # Gap 6 (new file)
```

---

## Priority Order

1. **Rate limit HTTP integration** - Highest risk, proves 429 actually returned
2. **Daily limit unit tests** - Medium risk, untested code path
3. **Auth cache HTTP integration** - Medium risk, proves cache wiring
4. **Null email handling** - Medium risk, common in production but untested
5. **Redis fallback HTTP** - Lower risk, unit tests cover most cases
6. **Edge cases** - Lowest risk, defensive coverage

---

## Success Criteria

After implementing these tests:

- [ ] Making 301 real HTTP requests returns 429 on the 301st
- [ ] Rate limit headers appear on all authenticated responses
- [ ] Daily limits block after per-minute limits pass
- [ ] Cache entries exist after authenticated requests
- [ ] `POST /consent/me` clears cache entries
- [ ] Requests succeed when Redis is unavailable
- [ ] Auth works for users without email (null email path)
