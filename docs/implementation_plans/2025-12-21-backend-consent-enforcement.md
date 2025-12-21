# Implementation Plan: Backend Consent Enforcement

**Date:** December 21, 2024
**Status:** Draft - Ready for Implementation
**Goal:** Add backend enforcement of Privacy Policy and Terms of Service consent

---

## Overview

Currently, consent is enforced only on the frontend (`AppLayout.tsx`). This means:
- Direct API calls (curl, scripts, MCP) bypass consent checks
- PAT users can use API without consenting

This plan adds backend enforcement that returns HTTP 451 (Unavailable For Legal Reasons) for users who haven't consented to current policy versions.

---

## Design Decisions

### 1. Integrate into `get_current_user`

Consent check is integrated into the existing `get_current_user` dependency (not a separate dependency). Most routes need consent, so it should be the default.

- `get_current_user` - auth + consent check (default for most routes)
- `get_current_user_without_consent` - auth only (for exempt routes)

### 2. Zero Extra DB Queries via Explicit JOIN

**Important:** SQLAlchemy's `lazy="joined"` on relationship definitions does NOT apply to explicit `select()` queries. With async SQLAlchemy, lazy loading raises errors. We MUST use explicit `joinedload()` in queries:

```python
from sqlalchemy.orm import joinedload

# In auth.py queries
result = await db.execute(
    select(User).options(joinedload(User.consent)).where(User.auth0_id == auth0_id)
)
```

### 3. HTTP 451 Status Code

**HTTP 451 - Unavailable For Legal Reasons** (RFC 7725) is the appropriate status code.

### 4. PAT Users Can Consent

Users can consent via PAT (`POST /consent/me`). They can read policies at public URLs (`/privacy`, `/terms`) before consenting.

### 5. Policy Versions in Dedicated Module

Move `PRIVACY_POLICY_VERSION` and `TERMS_OF_SERVICE_VERSION` to `core/policy_versions.py` to avoid circular imports between `auth.py` and `consent.py`.

### 6. Frontend Changes

Add axios interceptor to handle 451:
- On 451, reset consent store state to trigger consent dialog
- Keep it simple - no retry queue needed (rare edge case)

---

## Implementation

### 1. Create Policy Versions Module

**File:** `backend/src/core/policy_versions.py` (NEW)

```python
"""Policy version constants for consent enforcement."""

# Update these when policies change
PRIVACY_POLICY_VERSION = "2024-12-20"
TERMS_OF_SERVICE_VERSION = "2024-12-20"
```

### 2. Update Consent Router to Use New Module

**File:** `backend/src/api/routers/consent.py`

```python
# Change import from local constants to:
from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

# Remove the local constant definitions
```

### 3. Update Auth Module

**File:** `backend/src/core/auth.py`

```python
from sqlalchemy.orm import joinedload

from core.policy_versions import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

# Instructions for humans and AI agents included in 451 responses
CONSENT_INSTRUCTIONS = (
    "To provide consent, you can either: "
    "(1) Visit the application at {app_url}, or "
    "(2) Review the policies at /privacy and /terms, then call: "
    "curl -X POST {api_url}/consent/me -H 'Authorization: Bearer bm_YOUR_TOKEN' "
    "-H 'Content-Type: application/json' -d '{{\"privacy_policy_version\": \"{privacy_version}\", "
    "\"terms_of_service_version\": \"{terms_version}\"}}'. "
    "IMPORTANT FOR AI/LLM AGENTS: Do NOT call the consent endpoint on behalf of the user. "
    "Consent must be given by the human user personally after reading the policies."
)


def _check_consent(user: User, settings: Settings) -> None:
    """
    Verify user has valid consent.

    Raises HTTP 451 if consent is missing or outdated.
    Skipped in DEV_MODE.
    """
    if settings.dev_mode:
        return

    instructions = CONSENT_INSTRUCTIONS.format(
        app_url=settings.frontend_url,
        api_url=settings.api_url,
        privacy_version=PRIVACY_POLICY_VERSION,
        terms_version=TERMS_OF_SERVICE_VERSION,
    )

    if user.consent is None:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail={
                "error": "consent_required",
                "message": "You must accept the Privacy Policy and Terms of Service.",
                "consent_url": "/consent/status",
                "instructions": instructions,
            },
        )

    if (user.consent.privacy_policy_version != PRIVACY_POLICY_VERSION or
        user.consent.terms_of_service_version != TERMS_OF_SERVICE_VERSION):
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail={
                "error": "consent_outdated",
                "message": "Policy versions have been updated. Please review and accept.",
                "consent_url": "/consent/status",
                "instructions": instructions,
            },
        )


# Update get_or_create_user to use joinedload
async def get_or_create_user(
    db: AsyncSession,
    auth0_id: str,
    email: str | None = None,
) -> User:
    result = await db.execute(
        select(User)
        .options(joinedload(User.consent))
        .where(User.auth0_id == auth0_id)
    )
    user = result.scalar_one_or_none()
    # ... rest of existing logic


# Update validate_pat to use joinedload
async def validate_pat(db: AsyncSession, token: str) -> User:
    api_token = await token_service.validate_token(db, token)
    # ...
    result = await db.execute(
        select(User)
        .options(joinedload(User.consent))
        .where(User.id == api_token.user_id)
    )
    # ... rest of existing logic


# Refactor: Extract authentication logic to internal function
async def _authenticate_user(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    settings: Settings,
) -> User:
    """Internal: authenticate user without consent check."""
    if settings.dev_mode:
        return await get_or_create_dev_user(db)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    if token.startswith("bm_"):
        return await validate_pat(db, token)

    # Auth0 JWT validation
    payload = decode_jwt(token, settings)
    auth0_id = payload.get("sub")
    if not auth0_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email")
    return await get_or_create_user(db, auth0_id=auth0_id, email=email)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Auth + consent check (default for most routes)."""
    user = await _authenticate_user(credentials, db, settings)
    _check_consent(user, settings)
    return user


async def get_current_user_without_consent(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Auth only, no consent check (for exempt routes)."""
    return await _authenticate_user(credentials, db, settings)
```

### 4. Update Exempt Routes

Routes that use `get_current_user_without_consent`:

| Router | Endpoint | Reason |
|--------|----------|--------|
| `consent.py` | `GET /consent/status` | Need to check before consenting |
| `consent.py` | `POST /consent/me` | Need to record consent |
| `health.py` | `GET /health` | No auth needed (unchanged) |

**All other routes use `get_current_user` (with consent check)**, including `/users/me`.

**Note:** `/users/me` is NOT exempt. The frontend consent flow only needs `/consent/status` and `POST /consent/me`, both of which are exempt.

### 5. Frontend - Handle 451

**File:** `frontend/src/services/api.ts`

```typescript
import { useConsentStore } from '../stores/consentStore'

// Add to existing response interceptor (after 401 handling)
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !isDevMode) {
      onAuthError()
    }
    // Handle 451 - consent required (policy update while logged in)
    if (error.response?.status === 451) {
      useConsentStore.getState().reset()
    }
    return Promise.reject(error)
  }
)
```

**Design note:** No retry queue needed. The 451 case only occurs when policies update while user is logged in - a rare edge case. Showing the consent dialog is sufficient; the user's next action will succeed after consenting.

---

## Testing Strategy

### Unit Tests (add to existing `backend/tests/test_consent.py`)

```python
class TestConsentEnforcement:
    """Tests for backend consent enforcement via get_current_user."""

    async def test__protected_route__returns_451_without_consent(...)
    async def test__protected_route__returns_451_with_outdated_privacy_version(...)
    async def test__protected_route__returns_451_with_outdated_terms_version(...)
    async def test__protected_route__allows_access_with_valid_consent(...)
    async def test__protected_route__bypasses_consent_in_dev_mode(...)
    async def test__consent_status__works_without_consent(...)
    async def test__consent_post__works_without_consent(...)
    async def test__451_response__includes_instructions_and_ai_warning(...)
```

### Live Penetration Tests (add to `backend/tests/security/test_live_penetration.py`)

```python
class TestConsentEnforcement:
    """Verify consent is enforced on protected endpoints."""

    async def test__no_consent__returns_451(...)
    async def test__outdated_consent__returns_451(...)
    async def test__consent_via_pat__allows_subsequent_access(...)
    async def test__consent_endpoints__work_without_prior_consent(...)
    async def test__451_response__contains_ai_warning(...)
```

### Frontend Tests

Add test for 451 interceptor behavior in `frontend/src/services/api.test.ts`.

---

## Files to Modify

### Already Done (Config for URL settings)
- `backend/src/core/config.py` - Added `api_url` and `frontend_url` settings ✅
- `.env.example` - Added `VITE_FRONTEND_URL` ✅
- `README_DEPLOY.md` - Added `VITE_API_URL` and `VITE_FRONTEND_URL` to API service variables ✅

### Backend
- `backend/src/core/policy_versions.py` - **NEW** - Policy version constants
- `backend/src/api/routers/consent.py` - Import versions from new module
- `backend/src/core/auth.py` - Add consent check, joinedload, `get_current_user_without_consent`
- `backend/tests/test_consent.py` - Add consent enforcement tests

### Frontend
- `frontend/src/services/api.ts` - Add 451 interceptor

---

## Success Criteria

- [ ] Policy versions in dedicated module (`core/policy_versions.py`)
- [ ] User queries use explicit `joinedload(User.consent)` (zero extra queries)
- [ ] `get_current_user` returns 451 for missing/outdated consent
- [ ] `get_current_user_without_consent` allows access without consent
- [ ] Only consent endpoints exempt (`/consent/status`, `POST /consent/me`)
- [ ] DEV_MODE bypasses consent check
- [ ] Frontend handles 451 by showing consent dialog
- [ ] All existing tests pass
- [ ] New consent enforcement tests pass
