# Implementation Plan: Backend Consent Enforcement

**Date:** December 21, 2024
**Status:** Draft - Ready for Review
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

### 2. Zero Extra DB Queries via JOIN

Eager load consent when fetching user - no additional query:

```python
# User model
consent = relationship("UserConsent", uselist=False, lazy="joined")

# Already loaded when we have the user
if user.consent is None or user.consent.privacy_policy_version != CURRENT:
    raise HTTPException(451, ...)
```

### 3. HTTP 451 Status Code

**HTTP 451 - Unavailable For Legal Reasons** (RFC 7725) is the appropriate status code.

### 4. PAT Users Can Consent

Users can consent via PAT (`POST /consent/me`). They can read policies at public URLs (`/privacy`, `/terms`) before consenting.

### 5. Frontend Changes

Add axios interceptor to handle 451:
- On 451, set `needsConsent = true` in consent store
- Dialog will appear, user consents, retries work

This handles edge case: policy updates while user is logged in.

---

## Implementation

### 1. Update User Model - Add Consent Relationship

**File:** `backend/src/models/user.py`

```python
from models.user_consent import UserConsent

class User(Base):
    # ... existing fields ...

    # Eager load consent for zero-cost consent checks
    consent = relationship(
        "UserConsent",
        uselist=False,
        back_populates="user",
        lazy="joined",
    )
```

**File:** `backend/src/models/user_consent.py`

```python
# Add back_populates
user = relationship("User", back_populates="consent")
```

### 2. Update Auth Module

**File:** `backend/src/core/auth.py`

```python
from api.routers.consent import PRIVACY_POLICY_VERSION, TERMS_OF_SERVICE_VERSION

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


async def get_current_user(...) -> User:
    """Auth + consent check (default for most routes)."""
    user = await _authenticate_user(...)  # existing logic
    _check_consent(user, settings)
    return user


async def get_current_user_without_consent(...) -> User:
    """Auth only, no consent check (for exempt routes)."""
    return await _authenticate_user(...)
```

### 3. Update Exempt Routes

Routes that use `get_current_user_without_consent`:

| Router | Endpoint | Reason |
|--------|----------|--------|
| `consent.py` | `GET /consent/status` | Need to check before consenting |
| `consent.py` | `POST /consent/me` | Need to record consent |
| `users.py` | `GET /users/me` | May need user info before consent |
| `health.py` | `GET /health` | No auth needed (unchanged) |

All other routes use `get_current_user` (with consent check).

### 4. Frontend - Handle 451

**File:** `frontend/src/services/api.ts`

```typescript
import { useConsentStore } from '../stores/consentStore'

// Add response interceptor
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 451) {
      // Policy update while logged in - trigger consent dialog
      useConsentStore.getState().reset()
      // Optionally: store the failed request to retry after consent
    }
    return Promise.reject(error)
  }
)
```

---

## Testing Strategy

### Backend Tests

**File:** `backend/tests/test_consent_enforcement.py`

```python
class TestConsentEnforcement:
    """Tests for backend consent enforcement."""

    async def test__protected_route__returns_451_without_consent(...)
    async def test__protected_route__returns_451_with_outdated_consent(...)
    async def test__protected_route__allows_access_with_valid_consent(...)
    async def test__protected_route__bypasses_consent_in_dev_mode(...)
    async def test__consent_status__works_without_consent(...)
    async def test__consent_post__works_without_consent(...)
    async def test__users_me__works_without_consent(...)
```

### Frontend Tests

Add test for 451 interceptor behavior.

---

## Files to Modify

### Already Done (Config for URL settings)
- `backend/src/core/config.py` - Added `api_url` and `frontend_url` settings ✅
- `.env.example` - Added `VITE_FRONTEND_URL` ✅
- `README_DEPLOY.md` - Added `VITE_API_URL` and `VITE_FRONTEND_URL` to API service variables ✅

### Backend
- `backend/src/models/user.py` - Add consent relationship
- `backend/src/models/user_consent.py` - Add back_populates
- `backend/src/core/auth.py` - Add consent check, create `get_current_user_without_consent`
- `backend/src/api/routers/consent.py` - Use `get_current_user_without_consent`
- `backend/src/api/routers/users.py` - Use `get_current_user_without_consent`
- `backend/tests/test_consent_enforcement.py` - New tests

### Frontend
- `frontend/src/services/api.ts` - Add 451 interceptor

---

## Success Criteria

- [ ] User model eager loads consent (zero extra queries)
- [ ] `get_current_user` returns 451 for missing/outdated consent
- [ ] `get_current_user_without_consent` allows access without consent
- [ ] Consent endpoints work without prior consent
- [ ] DEV_MODE bypasses consent check
- [ ] Frontend handles 451 by showing consent dialog
- [ ] All existing tests pass
- [ ] New consent enforcement tests pass

---

## Estimated Effort

- Backend implementation: 2 hours
- Frontend 451 handler: 30 minutes
- Testing: 1.5 hours
- **Total: ~4 hours**
