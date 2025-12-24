# Redis-Based Rate Limiting and Auth Caching

## Overview

Add Redis for production-ready rate limiting and auth caching. The system should:

1. **Rate limit by auth type**: PATs get stricter limits than Auth0 tokens
2. **Rate limit by operation type**: Read vs Write vs Sensitive operations
3. **Enforce daily caps**: Prevent sustained abuse over time
4. **Cache auth lookups**: Reduce DB load per request (with proper invalidation)
5. **Fail open**: If Redis is unavailable, skip rate limiting and fall back to DB for auth
6. **Return rate limit headers**: `X-RateLimit-Remaining` and `X-RateLimit-Reset` on responses

## Key Design Decisions

### Rate Limit Tiers

Three operation types:
- **Read**: GET requests (browsing, searching)
- **Write**: POST, PATCH, DELETE requests (creating, updating, deleting)
- **Sensitive**: Operations with higher abuse potential (external HTTP calls, AI/LLM features in future)

| Operation | PAT | Auth0 | Rationale |
|-----------|-----|-------|-----------|
| **Read** | 120/min | 300/min | Higher tolerance for browsing |
| **Write** | 60/min | 90/min | Writes are expensive, PATs easier to abuse |
| **Sensitive** | N/A (blocked) | 30/min | SSRF risk, resource-intensive |
| **Daily (read/write)** | 2,000/day | 4,000/day | enough for the day accounting for peak usage |
| **Daily (sensitive)** | N/A | 250/day | Low-volume by nature, resource-intensive |

**Daily cap keys are separate:**
- `rate:{user_id}:daily:general` - shared pool for read/write operations
- `rate:{user_id}:daily:sensitive` - separate pool for sensitive operations

**Sensitive operations** (currently):
- `GET /bookmarks/fetch-metadata` - external HTTP requests, SSRF risk

**Future sensitive operations** (when added):
- AI/LLM summarization endpoints
- Bulk import/export

### Auth Cache Strategy

- **Cache key**: `auth:v{VERSION}:user:auth0:{auth0_id}` or `auth:v{VERSION}:user:id:{user_id}`
- **Schema versioning**: Bump `CACHE_SCHEMA_VERSION` when cached User fields change
- **TTL**: 5 minutes
- **Invalidation points**:
  - `POST /consent/me` → invalidate user cache
- **Schema mismatch handling**: Old version keys ignored (TTL cleans them up)

**Note:** Token revocation (`DELETE /tokens/{id}`) does NOT require cache invalidation. PAT validation always hits the DB to check the token hash - if revoked, validation fails before user cache is consulted.

### Observability

Use structured logging for exceptional events only (not cache hits - those are expected and high volume):

```python
# Cache miss - cold cache, after invalidation, or schema version bump
logger.info("auth_cache_miss", extra={"auth0_id": auth0_id})

# Rate limit exceeded - potential abuse
logger.warning("rate_limit_exceeded", extra={
    "user_id": user_id,
    "operation": operation_type.value,
    "auth_type": auth_type.value,
})

# Redis unavailable - operational issue, fallback triggered
logger.warning("redis_unavailable", extra={"operation": "rate_limit"})
```

Railway's log viewer supports filtering by these structured fields.

### Fallback Behavior

When Redis is unavailable:
- **Rate limiting**: Skip (fail open with warning log)
- **Auth cache**: Fall back to DB (cache miss behavior)

This ensures users aren't locked out during Redis outages.

---

## Milestone 1: Redis Infrastructure

### Goal
Set up Redis connectivity with testcontainers support and graceful fallback handling.

### Success Criteria
- Redis container in docker-compose for local dev
- Async Redis client with connection pooling
- Testcontainers fixture for Redis in pytest
- Health check endpoint reports Redis status
- Connection failures are handled gracefully (logged, not raised)

### Key Changes

**pyproject.toml** - Add Redis dependency:

`uv add redis`.. never modify pyproject.toml directly, but for example:

```toml
dependencies = [
    # ... existing deps ...
    "redis>=5.0.0",  # Async Redis client
]
```

**docker-compose.yml** - Add Redis service:
```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 3
```

**backend/src/core/config.py** - Add Redis settings:
```python
redis_url: str = "redis://localhost:6379"
redis_enabled: bool = True  # Can disable for local dev without Redis
```

**backend/src/core/redis.py** - New file for Redis connection management:
```python
import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

class RedisClient:
    """Async Redis client with connection pooling and graceful fallback."""

    def __init__(self, url: str, enabled: bool = True):
        self._url = url
        self._enabled = enabled
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    async def connect(self) -> None:
        """Initialize connection pool."""
        if not self._enabled:
            return
        self._pool = ConnectionPool.from_url(self._url, max_connections=10)
        self._client = Redis(connection_pool=self._pool)

    async def close(self) -> None:
        """Close connection pool."""
        if self._client:
            await self._client.close()

    async def get(self, key: str) -> bytes | None:
        """Get value, returns None if Redis unavailable."""
        if not self._client:
            return None
        try:
            return await self._client.get(key)
        except RedisError as e:
            logger.warning("Redis GET failed: %s", e)
            return None

    # Similar pattern for set, delete, incr, etc.
```

**backend/src/api/main.py** - Lifespan management:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await redis_client.connect()
    yield
    # Shutdown
    await redis_client.close()
```

**backend/tests/conftest.py** - Testcontainers fixture:
```python
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis

@pytest.fixture
async def redis_client(redis_container) -> AsyncGenerator[RedisClient, None]:
    client = RedisClient(redis_container.get_connection_url())
    await client.connect()
    yield client
    await client._client.flushdb()
    await client.close()
```

### Testing Strategy

1. **Connection tests**: Verify connect/disconnect lifecycle
2. **Fallback tests**: Verify graceful handling when Redis unavailable
3. **Health check tests**: Verify `/health` reports Redis status

### Dependencies
None - this is the foundation.

### Risk Factors
- Railway Redis connection string format may differ from local
- Need to handle both `redis://` and `rediss://` (TLS) URLs

---

## Milestone 2: Redis-Based Rate Limiting

### Goal
Replace in-memory rate limiter with Redis-based sliding window implementation supporting tiered limits.

### Success Criteria
- Rate limits enforced via Redis sorted sets (sliding window)
- Different limits for PAT vs Auth0 tokens
- Different limits for read vs write vs sensitive operations
- Daily caps in addition to per-minute limits
- Rate limit headers returned on all responses (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)
- Graceful fallback when Redis unavailable
- Existing `fetch_metadata_limiter` migrated to new system

### Key Changes

**backend/src/core/rate_limiter.py** - Replace with Redis implementation:
```python
from enum import Enum
from dataclasses import dataclass

class AuthType(Enum):
    PAT = "pat"
    AUTH0 = "auth0"

class OperationType(Enum):
    READ = "read"
    WRITE = "write"
    SENSITIVE = "sensitive"  # External HTTP calls, AI/LLM, bulk operations

@dataclass
class RateLimitConfig:
    requests_per_minute: int
    requests_per_day: int

# Limit configuration
# Daily caps: general (read/write) vs sensitive are tracked separately
RATE_LIMITS: dict[tuple[AuthType, OperationType], RateLimitConfig] = {
    (AuthType.PAT, OperationType.READ): RateLimitConfig(120, 2000),
    (AuthType.PAT, OperationType.WRITE): RateLimitConfig(30, 2000),
    # PAT + SENSITIVE = not allowed (handled separately, returns 403)
    (AuthType.AUTH0, OperationType.READ): RateLimitConfig(300, 5000),
    (AuthType.AUTH0, OperationType.WRITE): RateLimitConfig(60, 5000),
    (AuthType.AUTH0, OperationType.SENSITIVE): RateLimitConfig(15, 250),  # Separate daily key
}

# Daily cap Redis keys:
# - rate:{user_id}:daily:general   (shared by READ and WRITE)
# - rate:{user_id}:daily:sensitive (separate for SENSITIVE ops)

# Endpoints classified as SENSITIVE (require Auth0, stricter limits)
SENSITIVE_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/bookmarks/fetch-metadata"),
    # Future: AI/LLM endpoints, bulk operations
}

class RedisRateLimiter:
    """Redis-based sliding window rate limiter."""

    async def is_allowed(
        self,
        user_id: int,
        auth_type: AuthType,
        operation_type: OperationType,
    ) -> tuple[bool, int | None]:
        """
        Check if request is allowed.

        Returns:
            (allowed, retry_after_seconds or None)
        """
        config = RATE_LIMITS.get((auth_type, operation_type))
        if not config:
            return True, None  # No limit configured

        # Check minute limit
        minute_key = f"rate:{user_id}:{auth_type.value}:{operation_type.value}:min"
        minute_allowed, minute_retry = await self._check_window(
            minute_key, config.requests_per_minute, 60
        )
        if not minute_allowed:
            return False, minute_retry

        # Check daily limit
        day_key = f"rate:{user_id}:daily"
        day_allowed, day_retry = await self._check_window(
            day_key, config.requests_per_day, 86400
        )
        if not day_allowed:
            return False, day_retry

        return True, None

    async def _check_window(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int | None]:
        """Sliding window check using Redis sorted set."""
        # Implementation uses ZADD/ZREMRANGEBYSCORE/ZCARD pattern
        # Falls back to allowing if Redis unavailable
```

**backend/src/api/dependencies.py** - Add rate limit dependency:
```python
from core.rate_limiter import AuthType, OperationType, rate_limiter, SENSITIVE_ENDPOINTS

def _get_operation_type(method: str, path: str) -> OperationType:
    """Determine operation type from HTTP method and path."""
    if (method, path) in SENSITIVE_ENDPOINTS:
        return OperationType.SENSITIVE
    if method == "GET":
        return OperationType.READ
    return OperationType.WRITE

async def check_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Dependency that enforces rate limits.

    Reads auth_type from request.state (set by auth dependency).
    Stores rate limit info in request.state for middleware to add headers.
    """
    auth_type = getattr(request.state, "auth_type", AuthType.AUTH0)
    operation_type = _get_operation_type(request.method, request.url.path)

    result = await rate_limiter.check(
        current_user.id, auth_type, operation_type
    )

    # Store for middleware to add headers
    request.state.rate_limit_info = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset": result.reset,
    }

    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(result.retry_after)},
        )
```

**backend/src/api/middleware/rate_limit_headers.py** - Middleware for headers:
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Add rate limit headers to responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Add headers if rate limit info was stored by dependency
        info = getattr(request.state, "rate_limit_info", None)
        if info:
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response
```

**backend/src/api/main.py** - Register middleware:
```python
app.add_middleware(RateLimitHeadersMiddleware)
```

**Router changes** - Apply rate limiting:
- Remove inline rate limiting from `fetch_metadata` endpoint
- Rate limiting applied globally via dependency or middleware

### Testing Strategy

1. **Limit enforcement**: Verify requests blocked after limit reached
2. **Window sliding**: Verify old requests expire correctly
3. **Tier separation**: Verify PAT vs Auth0 have different limits
4. **Operation separation**: Verify read vs write vs sensitive have different limits
5. **Daily caps**: Verify daily limit enforced across operations
6. **Fallback**: Verify requests allowed when Redis unavailable
7. **Headers**: Verify `X-RateLimit-*` headers on all responses
8. **Retry-After header**: Verify correct value returned on 429

Key test cases:
```python
async def test__rate_limit__pat_write_blocked_at_30_per_minute()
async def test__rate_limit__auth0_write_allowed_up_to_60_per_minute()
async def test__rate_limit__sensitive_uses_15_per_minute_limit()
async def test__rate_limit__sensitive_daily_cap_250()
async def test__rate_limit__daily_cap_enforced_across_operations()
async def test__rate_limit__different_users_have_separate_buckets()
async def test__rate_limit__redis_down_fails_open()
async def test__rate_limit__headers_included_in_response()
async def test__rate_limit__headers_decrement_correctly()
```

### Dependencies
- Milestone 1 (Redis Infrastructure)

### Risk Factors
- Sliding window with sorted sets has Redis memory overhead
- Need to balance accuracy vs Redis operations per request
- Consider using Redis pipeline for atomic operations

---

## Milestone 3: Auth Caching

### Goal
Cache user lookups to reduce database load, with proper invalidation on consent and token changes.

### Success Criteria
- User objects cached in Redis with 5-minute TTL
- Cache hit skips database query
- Cache invalidated on `POST /consent/me`
- Cache invalidated on `DELETE /tokens/{id}`
- Falls back to DB when Redis unavailable or cache miss
- Cache keys properly namespaced by auth method

### Key Changes

**backend/src/schemas/cached_user.py** - New file for cached user representation:
```python
from dataclasses import dataclass

@dataclass
class CachedUser:
    """
    Lightweight user representation for auth caching.

    Avoids ORM reconstruction complexity - just the fields needed for auth checks.
    """
    id: int
    auth0_id: str
    email: str | None
    consent_privacy_version: str | None
    consent_tos_version: str | None
```

**backend/src/core/auth_cache.py** - New file:
```python
import json
import logging

from schemas.cached_user import CachedUser

logger = logging.getLogger(__name__)

# Bump this when CachedUser fields change
# Old versioned keys will be ignored and cleaned up by TTL
CACHE_SCHEMA_VERSION = 1

class AuthCache:
    """Cache for authenticated user lookups."""

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, redis_client):
        self._redis = redis_client

    def _cache_key_auth0(self, auth0_id: str) -> str:
        return f"auth:v{CACHE_SCHEMA_VERSION}:user:auth0:{auth0_id}"

    def _cache_key_user_id(self, user_id: int) -> str:
        return f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_id}"

    async def get_by_auth0_id(self, auth0_id: str) -> CachedUser | None:
        """Get cached user by Auth0 ID."""
        key = self._cache_key_auth0(auth0_id)
        data = await self._redis.get(key)
        if data:
            logger.info("auth_cache_hit", extra={"auth0_id": auth0_id})
            return self._deserialize(data)
        logger.info("auth_cache_miss", extra={"auth0_id": auth0_id})
        return None

    async def get_by_user_id(self, user_id: int) -> CachedUser | None:
        """Get cached user by user ID (for PAT lookups)."""
        key = self._cache_key_user_id(user_id)
        data = await self._redis.get(key)
        if data:
            return self._deserialize(data)
        logger.info("auth_cache_miss", extra={"user_id": user_id})
        return None

    async def set(self, user, auth0_id: str | None = None) -> None:
        """Cache user data from ORM User object."""
        cached = CachedUser(
            id=user.id,
            auth0_id=user.auth0_id,
            email=user.email,
            consent_privacy_version=user.consent.privacy_policy_version if user.consent else None,
            consent_tos_version=user.consent.terms_of_service_version if user.consent else None,
        )
        data = json.dumps(cached.__dict__)

        # Cache by user ID (for PAT lookups after token validation)
        await self._redis.setex(
            self._cache_key_user_id(user.id),
            self.CACHE_TTL,
            data,
        )

        # Also cache by auth0_id if provided (for Auth0 JWT lookups)
        if auth0_id:
            await self._redis.setex(
                self._cache_key_auth0(auth0_id),
                self.CACHE_TTL,
                data,
            )

    async def invalidate(self, user_id: int, auth0_id: str | None = None) -> None:
        """Invalidate cached user data."""
        await self._redis.delete(self._cache_key_user_id(user_id))
        if auth0_id:
            await self._redis.delete(self._cache_key_auth0(auth0_id))

    def _deserialize(self, data: bytes) -> CachedUser:
        """Deserialize cached data to CachedUser."""
        d = json.loads(data)
        return CachedUser(**d)
```

**backend/src/core/auth.py** - Integrate caching:
```python
from schemas.cached_user import CachedUser

async def get_or_create_user(
    db: AsyncSession,
    auth0_id: str,
    email: str | None = None,
) -> User | CachedUser:
    """
    Get user from cache or database.

    Returns CachedUser on cache hit, User ORM object on cache miss.
    Both have the fields needed for auth checks (id, auth0_id, email, consent).
    """
    # Try cache first
    cached = await auth_cache.get_by_auth0_id(auth0_id)
    if cached:
        return cached

    # Cache miss - hit DB
    result = await db.execute(
        select(User)
        .options(joinedload(User.consent))
        .where(User.auth0_id == auth0_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Create new user...
        user = User(auth0_id=auth0_id, email=email)
        db.add(user)
        await db.flush()

    # Populate cache
    await auth_cache.set(user, auth0_id)

    return user

# Store auth type in request.state for rate limiting
async def _authenticate_user(...) -> User | CachedUser:
    # ... existing logic ...

    if token.startswith("bm_"):
        request.state.auth_type = AuthType.PAT
        # ... PAT validation ...
    else:
        request.state.auth_type = AuthType.AUTH0
        # ... JWT validation ...
```

**backend/src/api/routers/consent.py** - Invalidate on consent update:
```python
@router.post("/me", ...)
async def record_consent(...):
    # ... existing logic ...

    # Invalidate cache after consent update
    await auth_cache.invalidate(current_user.id, current_user.auth0_id)

    return response
```

**Note:** Token revocation (`DELETE /tokens/{id}`) does NOT need cache invalidation - PAT validation hits the DB directly, so revoked tokens fail before cache is consulted.

### Testing Strategy

1. **Cache hit**: Verify CachedUser returned without DB query
2. **Cache miss**: Verify DB queried and cache populated
3. **TTL expiry**: Verify cache expires after 5 minutes
4. **Consent invalidation**: Verify cache cleared on consent update
5. **Fallback**: Verify DB queried when Redis unavailable
6. **Schema versioning**: Verify old version keys ignored after version bump
7. **PAT caching**: Verify PAT auth uses user_id cache after token validation

Key test cases:
```python
async def test__auth_cache__cache_hit_returns_cached_user():
    """Verify cached user returned without DB query."""

async def test__auth_cache__cache_miss_populates_cache():
    """Verify DB query result is cached for subsequent requests."""

async def test__auth_cache__consent_update_invalidates_cache():
    """Verify POST /consent/me clears user from cache."""

async def test__auth_cache__redis_down_falls_back_to_db():
    """Verify auth works when Redis unavailable."""

async def test__auth_cache__schema_version_mismatch_causes_cache_miss():
    """Verify old schema version keys are ignored."""
    # Manually write a cache entry with old version (v0)
    old_key = "auth:v0:user:auth0:test|123"
    await redis_client.set(old_key, '{"id": 1, "email": "old@test.com"}')

    # Current code uses v1, should miss and hit DB
    user = await get_or_create_user(db, auth0_id="test|123", email="new@test.com")

    # Should get fresh data from DB, not stale cache
    assert user.email == "new@test.com"

async def test__auth_cache__pat_lookup_uses_user_id_cache():
    """Verify PAT auth benefits from user cache after token validation."""
```

### Dependencies
- Milestone 1 (Redis Infrastructure)
- Can be done in parallel with Milestone 2

### Risk Factors
- Cached consent data could become stale if invalidation missed
- Need to decide: cache full User ORM object or minimal dict?
- Reconstructing User from cache needs careful handling of relationships

---

## Milestone 4: Integration and Documentation

### Goal
Wire everything together, add monitoring, and update documentation.

### Success Criteria
- Rate limiting active on all endpoints
- Auth caching integrated with existing auth flow
- `/health` endpoint reports Redis status
- Logging for rate limit exceeded and cache misses
- Frontend displays user-friendly error on 429 (not generic error)
- CLAUDE.md updated with Redis information
- README_DEPLOY.md updated with Redis setup for Railway
- Makefile updated with Redis commands

### Key Changes

**backend/src/api/routers/health.py** - Add Redis status:
```python
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": await check_db_health(),
        "redis": await check_redis_health(),  # New
    }
```

**Makefile** - Add Redis commands:
```makefile
redis-up:
    docker-compose up -d redis

redis-cli:
    docker-compose exec redis redis-cli
```

**README_DEPLOY.md** - Add Redis setup for Railway:
```markdown
### Step X: Add Redis

In the Railway dashboard:
1. Press `Cmd+K` (Mac) or `Ctrl+K` (Windows)
2. Type "Redis" and select **Add Redis**

Railway automatically creates the `REDIS_URL` variable on the Redis service.

#### API Service Variables (add)

```
REDIS_URL=${{Redis.REDIS_URL}}
```

**Note:** Railway Redis uses `redis://` by default. The app handles both `redis://` (local) and `rediss://` (TLS, production) URLs automatically.
```

**CLAUDE.md** - Document Redis:
```markdown
## Redis

Used for rate limiting and auth caching.

```bash
make redis-up      # Start Redis container
make redis-cli     # Connect to Redis CLI
```

### Rate Limits

Three operation types: **Read**, **Write**, **Sensitive**

| Operation | PAT | Auth0 |
|-----------|-----|-------|
| Read | 120/min | 300/min |
| Write | 30/min | 60/min |
| Sensitive | N/A (403) | 15/min |
| Daily (read/write) | 2,000/day | 5,000/day |
| Daily (sensitive) | N/A | 250/day |

**Sensitive endpoints** (Auth0-only, stricter limits):
- `GET /bookmarks/fetch-metadata`
- Future: AI/LLM endpoints

All responses include rate limit headers:
- `X-RateLimit-Limit`: Max requests in window
- `X-RateLimit-Remaining`: Requests left
- `X-RateLimit-Reset`: Unix timestamp when window resets

### Cache Invalidation
Auth cache invalidated on:
- POST /consent/me

Note: Token revocation does NOT invalidate cache - PAT validation always hits DB.
```

**frontend/src/services/api.ts** - Handle 429 responses:
```typescript
// In API client error handling
if (error.response?.status === 429) {
    const retryAfter = error.response.headers['retry-after'];
    const message = retryAfter
        ? `Too many requests. Please wait ${retryAfter} seconds.`
        : 'Too many requests. Please try again later.';

    // Show user-friendly toast/notification instead of generic error
    showToast(message, 'warning');

    // Don't propagate as generic error
    return Promise.reject(new RateLimitError(message, retryAfter));
}
```

**frontend/src/errors.ts** - Add RateLimitError class:
```typescript
export class RateLimitError extends Error {
    constructor(
        message: string,
        public retryAfter?: number
    ) {
        super(message);
        this.name = 'RateLimitError';
    }
}
```

### Testing Strategy

1. **End-to-end**: Full request flow with rate limiting and caching
2. **Health check**: Verify Redis status reported correctly
3. **Degraded mode**: Verify app works with Redis down
4. **Frontend 429**: Verify user-friendly error displayed on rate limit

### Dependencies
- Milestones 1, 2, 3

### Risk Factors
- Railway environment variables for Redis URL
- May need different Redis URL format for production

---

## Implementation Notes

### Redis Lua Scripts

For atomic sliding window operations, consider using Lua scripts:

```lua
-- Sliding window rate limit check
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove old entries
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add new entry
    redis.call('ZADD', key, now, now .. ':' .. math.random())
    redis.call('EXPIRE', key, window)
    return {1, 0}  -- allowed, no retry needed
else
    -- Get oldest entry for retry-after calculation
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = (oldest[2] + window) - now
    return {0, math.ceil(retry_after)}  -- denied, retry after
end
```

### Railway Deployment

Railway Redis addon provides:
- `REDIS_URL` environment variable
- TLS by default (`rediss://`)
- Connection pooling handled by Railway

Update `config.py` to read from environment:
```python
redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
```
