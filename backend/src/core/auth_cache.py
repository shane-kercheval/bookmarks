"""Authentication caching for reduced database load."""
import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from schemas.cached_user import CachedUser

if TYPE_CHECKING:
    from core.redis import RedisClient
    from models.user import User

logger = logging.getLogger(__name__)

# Cache schema version - included in all cache keys (e.g., "auth:v1:user:...")
#
# Bump this version when CachedUser fields change or when a deployment
# requires immediate cache invalidation (e.g., tier migrations).
# This ensures old cached entries (with the previous version) are ignored:
# - New code looks for "auth:v2:..." keys
# - Old "auth:v1:..." keys are never found (cache miss)
# - Old entries expire naturally via TTL (5 minutes)
#
# This avoids the need for cache invalidation during deployments.
# Version history:
#   v1: Initial version with id: int
#   v2: Changed id from int to UUID (UUIDv7 migration)
#   v3: Added tier field for tier-based limits
#   v4: Added email_verified field
#   v5: All users migrated to Pro for beta
#   v6: Added external_auth_id; auth0_id became optional (Clerk dual-accept)
#   v7: Removed auth0_id and the auth0 key segment (M6b decommission)
CACHE_SCHEMA_VERSION = 7


class AuthCache:
    """
    Cache for authenticated user lookups.

    A user entry is cached under every identifier that can authenticate it:
    - `id:{user_id}` — PAT flow lookups
    - `ext:{external_auth_id}` — Clerk JWT lookups (token `sub`)

    Invalidation must cover every segment the user may be cached under —
    see invalidate().
    """

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, redis_client: "RedisClient") -> None:
        """Initialize auth cache with Redis client."""
        self._redis = redis_client

    def _cache_key_external(self, external_auth_id: str) -> str:
        """Generate cache key for external auth ID (Clerk `sub`) lookup."""
        return f"auth:v{CACHE_SCHEMA_VERSION}:user:ext:{external_auth_id}"

    def _cache_key_user_id(self, user_id: UUID) -> str:
        """Generate cache key for user ID lookup."""
        return f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_id}"

    async def get_by_external_auth_id(self, external_auth_id: str) -> CachedUser | None:
        """
        Get cached user by external auth ID.

        Args:
            external_auth_id: The verified token's sub claim (the Clerk user ID).

        Returns:
            CachedUser if found in cache, None on cache miss.
        """
        key = self._cache_key_external(external_auth_id)
        data = await self._redis.get(key)
        if data:
            logger.debug("auth_cache_hit external_auth_id=%s", external_auth_id)
            return self._deserialize(data)
        logger.debug("auth_cache_miss external_auth_id=%s", external_auth_id)
        return None

    async def get_by_user_id(self, user_id: UUID) -> CachedUser | None:
        """
        Get cached user by user ID (for PAT lookups).

        Args:
            user_id: The database user ID (UUID).

        Returns:
            CachedUser if found in cache, None on cache miss.
        """
        key = self._cache_key_user_id(user_id)
        data = await self._redis.get(key)
        if data:
            logger.debug("auth_cache_hit user_id=%s", user_id)
            return self._deserialize(data)
        logger.debug("auth_cache_miss user_id=%s", user_id)
        return None

    async def set(self, user: "User") -> None:
        """
        Cache user data from ORM User object.

        Caches by user_id always, and by external_auth_id when the row carries
        one — so both auth paths (PAT, Clerk JWT) hit the same entry.

        Args:
            user: The User ORM object to cache.
        """
        cached = CachedUser(
            id=user.id,
            external_auth_id=user.external_auth_id,
            email=user.email,
            email_verified=user.email_verified,
            consent_privacy_version=(
                user.consent.privacy_policy_version if user.consent else None
            ),
            consent_tos_version=(
                user.consent.terms_of_service_version if user.consent else None
            ),
            tier=user.tier,
        )
        # Convert UUID to string for JSON serialization
        cache_dict = cached.__dict__.copy()
        cache_dict["id"] = str(cached.id)
        data = json.dumps(cache_dict)

        # Cache by user ID (for PAT lookups after token validation)
        await self._redis.setex(
            self._cache_key_user_id(user.id),
            self.CACHE_TTL,
            data,
        )

        if user.external_auth_id:
            await self._redis.setex(
                self._cache_key_external(user.external_auth_id),
                self.CACHE_TTL,
                data,
            )

        logger.debug(
            "auth_cache_set user_id=%s external_auth_id=%s",
            user.id,
            user.external_auth_id,
        )

    async def invalidate(
        self,
        user_id: UUID,
        external_auth_id: str | None = None,
    ) -> bool:
        """
        Invalidate cached user data.

        Should be called when user data changes (e.g., consent update).

        Callers MUST pass the external_auth_id when the user carries one — a
        segment left out keeps serving stale data for up to the TTL (the
        consent flow does; see api/routers/consent.py).

        Args:
            user_id: The database user ID.
            external_auth_id: External auth ID to also invalidate, if the user has one.

        Returns:
            False if Redis was unavailable and the keys may still be cached —
            the underlying client fails open, so callers for whom staleness is
            unacceptable (account deletion) must check this and fail loudly;
            best-effort callers (consent) may ignore it (staleness there is
            bounded by the TTL and self-corrects).
        """
        keys = [self._cache_key_user_id(user_id)]
        if external_auth_id:
            keys.append(self._cache_key_external(external_auth_id))
        deleted = await self._redis.delete(*keys)
        logger.debug(
            "auth_cache_invalidate user_id=%s external_auth_id=%s ok=%s",
            user_id,
            external_auth_id,
            deleted,
        )
        return deleted

    def _deserialize(self, data: bytes) -> CachedUser:
        """Deserialize cached data to CachedUser."""
        d = json.loads(data)
        # Convert id back to UUID
        d["id"] = UUID(d["id"])
        return CachedUser(**d)


# Global auth cache instance (set during app startup)
_auth_cache: AuthCache | None = None


def get_auth_cache() -> AuthCache | None:
    """Get the global auth cache instance."""
    return _auth_cache


def set_auth_cache(cache: AuthCache | None) -> None:
    """Set the global auth cache instance."""
    global _auth_cache  # noqa: PLW0603
    _auth_cache = cache
