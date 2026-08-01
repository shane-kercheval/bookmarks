"""Cached user representation for auth caching."""
from dataclasses import dataclass
from uuid import UUID


@dataclass
class CachedUser:
    """
    Lightweight user representation for auth caching.

    Avoids ORM reconstruction complexity - just the fields needed for auth checks.

    IMPORTANT: When adding, removing, or renaming fields in this class, you MUST bump
    CACHE_SCHEMA_VERSION in core/auth_cache.py. This ensures old cached entries (with
    the previous schema) are ignored and expire naturally via TTL. Without bumping
    the version, deserialization will fail or return stale/incorrect data.

    Safe attributes (available on both CachedUser and User ORM):
    - id: UUID
    - external_auth_id: str (NOT NULL since the M6b decommission migration)
    - email: str | None

    Consent fields (different access patterns):
    - CachedUser: consent_privacy_version, consent_tos_version (direct attributes)
    - User ORM: consent.privacy_policy_version, consent.terms_of_service_version

    WARNING: Do NOT access ORM relationships like .bookmarks, .tokens on CachedUser.
    Those only exist on User ORM objects.
    """

    id: UUID
    external_auth_id: str
    email: str | None
    email_verified: bool | None
    consent_privacy_version: str | None
    consent_tos_version: str | None
    tier: str
