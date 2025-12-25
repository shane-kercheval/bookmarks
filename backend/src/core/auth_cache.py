"""Authentication caching for reduced database load."""
import json
import logging
from typing import TYPE_CHECKING

from schemas.cached_user import CachedUser

if TYPE_CHECKING:
    from core.redis import RedisClient
    from models.user import User

logger = logging.getLogger(__name__)

# Cache schema version - included in all cache keys (e.g., "auth:v1:user:...")
#
# Bump this version when CachedUser fields are added, removed, or renamed.
# This ensures old cached entries (with the previous schema) are ignored:
# - New code looks for "auth:v2:..." keys
# - Old "auth:v1:..." keys are never found (cache miss)
# - Old entries expire naturally via TTL (5 minutes)
#
# This avoids the need for cache invalidation during deployments.
CACHE_SCHEMA_VERSION = 1


class AuthCache:
    """
    Cache for authenticated user lookups.

    Caches user data by both auth0_id and user_id for efficient lookups
    from both Auth0 JWT and PAT authentication flows.
    """

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, redis_client: "RedisClient") -> None:
        """Initialize auth cache with Redis client."""
        self._redis = redis_client

    def _cache_key_auth0(self, auth0_id: str) -> str:
        """Generate cache key for Auth0 ID lookup."""
        return f"auth:v{CACHE_SCHEMA_VERSION}:user:auth0:{auth0_id}"

    def _cache_key_user_id(self, user_id: int) -> str:
        """Generate cache key for user ID lookup."""
        return f"auth:v{CACHE_SCHEMA_VERSION}:user:id:{user_id}"

    async def get_by_auth0_id(self, auth0_id: str) -> CachedUser | None:
        """
        Get cached user by Auth0 ID.

        Args:
            auth0_id: The Auth0 sub claim (e.g., 'auth0|123456').

        Returns:
            CachedUser if found in cache, None on cache miss.
        """
        key = self._cache_key_auth0(auth0_id)
        data = await self._redis.get(key)
        if data:
            logger.debug("auth_cache_hit auth0_id=%s", auth0_id)
            return self._deserialize(data)
        logger.debug("auth_cache_miss auth0_id=%s", auth0_id)
        return None

    async def get_by_user_id(self, user_id: int) -> CachedUser | None:
        """
        Get cached user by user ID (for PAT lookups).

        Args:
            user_id: The database user ID.

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

    async def set(self, user: "User", auth0_id: str | None = None) -> None:
        """
        Cache user data from ORM User object.

        Caches by user_id always, and by auth0_id if provided.

        Args:
            user: The User ORM object to cache.
            auth0_id: Optional Auth0 ID for dual-key caching.
        """
        cached = CachedUser(
            id=user.id,
            auth0_id=user.auth0_id,
            email=user.email,
            consent_privacy_version=(
                user.consent.privacy_policy_version if user.consent else None
            ),
            consent_tos_version=(
                user.consent.terms_of_service_version if user.consent else None
            ),
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

        logger.debug(
            "auth_cache_set user_id=%s auth0_id=%s",
            user.id,
            auth0_id or user.auth0_id,
        )

    async def invalidate(self, user_id: int, auth0_id: str | None = None) -> None:
        """
        Invalidate cached user data.

        Should be called when user data changes (e.g., consent update).

        Args:
            user_id: The database user ID.
            auth0_id: Optional Auth0 ID to also invalidate.
        """
        keys = [self._cache_key_user_id(user_id)]
        if auth0_id:
            keys.append(self._cache_key_auth0(auth0_id))
        await self._redis.delete(*keys)
        logger.debug(
            "auth_cache_invalidate user_id=%s auth0_id=%s",
            user_id,
            auth0_id,
        )

    def _deserialize(self, data: bytes) -> CachedUser:
        """Deserialize cached data to CachedUser."""
        d = json.loads(data)
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
