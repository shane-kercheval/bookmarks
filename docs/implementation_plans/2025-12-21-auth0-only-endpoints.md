# Implementation Plan: Auth0-Only Endpoint Access Control

## Context

Currently, all protected endpoints accept both Auth0 JWT tokens (from the frontend) and Personal Access Tokens (PATs, prefixed with `bm_`). Some endpoints like `/bookmarks/fetch-metadata` should block PAT access to help prevent unintended programmatic use.

**Why restrict PAT access to fetch-metadata:**
- The endpoint makes external HTTP requests to arbitrary URLs (potential SSRF vector)
- Blocking PATs prevents compromised tokens from being used for SSRF abuse
- Rate limiting (15 req/min) provides additional protection
- No legitimate use case for PAT access to this endpoint

**Important limitation:** Blocking PATs does NOT prevent all programmatic access. Users can
extract their Auth0 JWT from browser DevTools and use it in scripts. Rate limiting is the
additional layer that caps any abuse.

**Current architecture (backend/src/core/auth.py):**
- `_authenticate_user` (internal) accepts both Auth0 JWTs and PATs (line 278: checks `bm_` prefix)
- `get_current_user` (public) = auth + consent check (default for most endpoints)
- `get_current_user_without_consent` (public) = auth only, no consent (for consent endpoints)
- `_check_consent` (internal) validates GDPR consent, returns HTTP 451 if missing/outdated

## Goal

Create new authentication dependencies that explicitly reject PATs, allowing only Auth0 JWT tokens. Follow the existing pattern with separate consent/no-consent variants. Apply `get_current_user_auth0_only` to `/bookmarks/fetch-metadata` to block PAT access and help prevent unintended programmatic use.

---

## Milestone 1: Create Auth0-Only Authentication Dependencies

**Goal**: Implement Auth0-only authentication following the existing pattern with internal/public and consent/no-consent variants.

**Success Criteria**:
- New internal function `_authenticate_user_auth0_only` in `backend/src/core/auth.py`
- New public dependencies `get_current_user_auth0_only` and `get_current_user_auth0_only_without_consent`
- Exported from `backend/src/api/dependencies.py`
- Rejects PATs with 403 Forbidden status
- Returns helpful error message: "This endpoint is not available for API tokens. Please use the web interface."
- Accepts Auth0 JWTs normally (same validation as existing code)
- Respects DEV_MODE (returns dev user when `settings.dev_mode=true`)
- Integrates with existing consent enforcement

**Key Changes**:

1. **Add internal auth function to `backend/src/core/auth.py`:**
   - Create `_authenticate_user_auth0_only` (similar to `_authenticate_user` at line 251)
   - Use same signature: `(credentials, db, settings) -> User`
   - Implementation:
     - Copy logic from `_authenticate_user` BUT:
     - **Reject PATs** at line where it checks `token.startswith("bm_")`:
       ```python
       if token.startswith("bm_"):
           raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="This endpoint is not available for API tokens. Please use the web interface.",
           )
       ```
     - Keep all other logic identical (dev mode, credentials check, JWT validation)
   - Place this function right after `_authenticate_user` (before line 297)

2. **Add public dependency with consent check:**
   - Create `get_current_user_auth0_only` (similar to `get_current_user` at line 297)
   - Calls `_authenticate_user_auth0_only` + `_check_consent`
   - Pattern:
     ```python
     async def get_current_user_auth0_only(...) -> User:
         """Auth0-only + consent check (blocks PAT access)."""
         user = await _authenticate_user_auth0_only(credentials, db, settings)
         _check_consent(user, settings)
         return user
     ```

3. **Add public dependency without consent check (optional but recommended):**
   - Create `get_current_user_auth0_only_without_consent` (similar to `get_current_user_without_consent` at line 313)
   - Just calls `_authenticate_user_auth0_only` (no consent)
   - Useful for consent/settings pages that should block PAT access

4. **Export from `backend/src/api/dependencies.py`:**
   - Add both new dependencies to imports (line 2)
   - Add both to `__all__` list (lines 6-11)

**Testing Strategy**:

Unit tests in `backend/tests/test_auth_auth0_only.py` (new file, similar to existing test patterns):
- Test `_authenticate_user_auth0_only`:
  - With valid Auth0 JWT → returns user
  - With PAT token → raises 403 with correct error message
  - With no token → raises 401
  - With invalid token → raises 401
  - In DEV_MODE → returns dev user (even with PAT - dev mode bypasses all checks)
- Test `get_current_user_auth0_only`:
  - Valid Auth0 user with consent → returns user
  - Valid Auth0 user without consent → raises 451
  - PAT token → raises 403 (auth fails before consent check)
- Test `get_current_user_auth0_only_without_consent`:
  - Valid Auth0 user (regardless of consent) → returns user
  - PAT token → raises 403

Note: Follow existing test patterns from `backend/tests/test_consent.py` for consent-related assertions

**Dependencies**: None

**Risk Factors**:
- None - this is purely additive, no existing code is modified
- The new dependency is similar to existing `get_current_user` with one additional check

---

## Milestone 2: Apply to fetch-metadata Endpoint

**Goal**: Block PAT access to `/bookmarks/fetch-metadata` using the new dependency.

**Success Criteria**:
- Endpoint uses `get_current_user_auth0_only` dependency instead of `get_current_user`
- Frontend users can still access the endpoint normally
- PAT requests return 403 with clear error message
- Existing unit tests still pass
- Rate limiting still works correctly

**Key Changes**:

1. **Update `backend/src/api/routers/bookmarks.py`:**
   - Line 9: Import `get_current_user_auth0_only` from `api.dependencies`
   - Line 35: Change dependency from `Depends(get_current_user)` to `Depends(get_current_user_auth0_only)`
   - Keep all other logic unchanged (rate limiting, URL fetching, etc.)

2. **Verify no other endpoints need this protection:**
   - Review all endpoints in `backend/src/api/routers/`
   - Document decision for each endpoint that might need to block PAT access
   - Currently only `/bookmarks/fetch-metadata` requires this restriction

**Testing Strategy**:

Unit tests in `backend/tests/api/test_bookmarks.py`:
- Add `test__fetch_metadata__rejects_pat_tokens` test:
  - Override `get_current_user_auth0_only` to raise 403
  - Verify endpoint returns 403
  - Verify error message matches expected text
- Add `test__fetch_metadata__accepts_auth0_tokens` test:
  - Use normal client fixture (simulates Auth0 auth in DEV_MODE)
  - Verify endpoint works normally (200 response)
  - Verify rate limiting still applies
- Ensure existing `fetch_metadata` tests still pass

**Dependencies**: Milestone 1 must be complete

**Risk Factors**:
- Existing code that uses PATs to call this endpoint will break
  - **Mitigation**: Check MCP server code (`backend/src/mcp_server/`) to ensure it doesn't use fetch-metadata
  - **Mitigation**: Search for any scripts or tools that might call this endpoint
- Frontend must use Auth0 tokens (not PATs) - verify this is already the case
  - **Verification**: Check `frontend/src/hooks/useBookmarks.ts` for how it's called

---

## Milestone 3: Add Live Penetration Tests

**Goal**: Verify PAT rejection works against deployed environment with real authentication.

**Success Criteria**:
- New test in `backend/tests/security/test_live_penetration.py` verifies PATs are rejected
- Test uses actual PAT from environment variables (like other live tests)
- Test runs against deployed API (not local DEV_MODE)
- Test is skipped if environment variables not set (like other live tests)

**Key Changes**:

1. **Add test to `backend/tests/security/test_live_penetration.py`:**
   - Add new test class `TestFrontendOnlyEndpoints`
   - Add test: `test__fetch_metadata__rejects_pat`
     - Use `headers_user_a` fixture (contains valid PAT)
     - Make GET request to `/bookmarks/fetch-metadata?url=https://example.com`
     - Assert status code is 403 (not 401, not 200)
     - Assert error message matches expected text
     - Verify security: PATs cannot abuse this endpoint
   - Follow existing test patterns (async, uses fixtures, has security assertion message)

2. **Update test documentation:**
   - Add comment explaining why this endpoint blocks PAT access
   - Reference SSRF protection as motivation

**Testing Strategy**:

Run against deployed environment:
```bash
# Requires SECURITY_TEST_API_URL and PAT tokens in .env
uv run pytest backend/tests/security/test_live_penetration.py::TestFrontendOnlyEndpoints -v
```

Verify:
- Test passes when endpoint correctly rejects PATs (403)
- Test would fail if endpoint accepts PATs (200) - indicating vulnerability
- Test is skipped in CI/CD without environment variables

**Dependencies**: Milestone 2 must be complete (endpoint must use new dependency)

**Risk Factors**:
- Test requires deployed environment to run
- Test is skipped in regular test runs (by design)
- Need to ensure at least one CI/CD environment runs these tests

---

## Milestone 4: Documentation

**Goal**: Document the new auth pattern for future endpoint development.

**Success Criteria**:
- CLAUDE.md updated with guidance on when to use which dependency
- Code comments explain the difference between dependencies
- README includes example of PAT-restricted endpoint

**Key Changes**:

1. **Update `CLAUDE.md`:**
   - Add section under "Architecture > Backend > api/" explaining the four dependency patterns:
     - `get_current_user`: Auth (Auth0 + PATs) + consent check - **default for most endpoints**
     - `get_current_user_without_consent`: Auth (Auth0 + PATs) - for consent/policy endpoints
     - `get_current_user_auth0_only`: Auth0 only + consent check - blocks PAT access
     - `get_current_user_auth0_only_without_consent`: Auth0 only - blocks PAT access, no consent check
   - Add decision criteria:
     - Default: use `get_current_user` (accepts Auth0 + PATs, requires consent)
     - Use `_without_consent` variants only for consent/policy viewing endpoints
     - Use `_auth0_only` variants to block PAT access where there's no legitimate PAT use case
   - Add note: `_auth0_only` does NOT block all programmatic access (users can extract Auth0 JWTs from browser DevTools)
   - Add table showing which dependency to use for common scenarios

2. **Add docstring to `get_current_user_auth0_only`:**
   - Explain when to use this dependency
   - List example use cases (metadata fetching, file uploads, etc.)
   - Note the 403 vs 401 status code semantics

3. **Update README.md:**
   - Add section on "Authentication Patterns"
   - Explain PATs vs Auth0 tokens
   - Document PAT-restricted endpoints pattern

**Testing Strategy**:
- Documentation review (no automated tests)
- Verify examples are accurate
- Ensure guidance is clear for future developers

**Dependencies**: Milestones 1-3 must be complete

**Risk Factors**: None - documentation only

---

## Implementation Notes

### Code Pattern to Follow

Follow the existing layered architecture in `backend/src/core/auth.py`:

**Internal auth function (similar to `_authenticate_user` at line 251):**
```python
async def _authenticate_user_auth0_only(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    settings: Settings,
) -> User:
    """
    Internal: authenticate user via Auth0 JWT only (rejects PATs).

    Blocks PAT access to help prevent unintended programmatic use.
    Note: Does NOT block Auth0 JWTs used outside the browser.
    In DEV_MODE, bypasses auth and returns a test user.
    """
    if settings.dev_mode:
        return await get_or_create_dev_user(db)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Reject PATs to help prevent unintended programmatic use
    if token.startswith("bm_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is not available for API tokens. Please use the web interface.",
        )

    # Auth0 JWT validation (same as _authenticate_user)
    payload = decode_jwt(token, settings)

    # Extract user info from JWT claims
    auth0_id = payload.get("sub")
    if not auth0_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email")
    return await get_or_create_user(db, auth0_id=auth0_id, email=email)
```

**Public dependencies (similar to `get_current_user` and `get_current_user_without_consent`):**
```python
async def get_current_user_auth0_only(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Dependency: Auth0-only auth + consent check (blocks PAT access).

    Use to block PAT access and help prevent unintended programmatic use.
    Examples:
    - /bookmarks/fetch-metadata (blocks PAT-based SSRF abuse)
    - /tokens/* (prevents compromised PAT from creating more tokens)

    Note: Does NOT prevent all programmatic access. Users can extract their
    Auth0 JWT from browser DevTools. Rate limiting caps any abuse.

    Returns 403 Forbidden for PAT tokens.
    Returns 451 if user hasn't consented to privacy policy/terms.
    """
    user = await _authenticate_user_auth0_only(credentials, db, settings)
    _check_consent(user, settings)
    return user


async def get_current_user_auth0_only_without_consent(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Dependency: Auth0-only auth, no consent check (blocks PAT access).

    Use to block PAT access on routes that must be accessible without consent.
    """
    return await _authenticate_user_auth0_only(credentials, db, settings)
```

### Testing Pattern

For unit tests, use dependency override to simulate different auth scenarios:

```python
# Test PAT rejection
async def test__endpoint__rejects_pat(client: AsyncClient) -> None:
    from api.main import app
    from api.dependencies import get_current_user_auth0_only

    async def mock_auth_reject_pat():
        raise HTTPException(status_code=403, detail="...")

    app.dependency_overrides[get_current_user_auth0_only] = mock_auth_reject_pat

    response = await client.get("/endpoint")
    assert response.status_code == 403

    app.dependency_overrides.clear()
```

For live tests, use actual PATs from environment:

```python
async def test__endpoint__rejects_pat(headers_user_a: dict[str, str]) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/endpoint",
            headers=headers_user_a,  # Contains real PAT
        )
    assert response.status_code == 403
```

### Rollout Strategy

1. Deploy backend changes first
2. Monitor logs for 403 responses to `/bookmarks/fetch-metadata`
3. If unexpected 403s appear, investigate (may indicate incorrect auth setup)
4. No frontend changes needed (frontend already uses Auth0 tokens)

### Future Considerations

**Endpoints that might need to block PAT access later:**
- None currently identified
- Pattern is now established for future use

**Alternative patterns if more granularity needed:**
- Scope-based permissions (Auth0 scopes vs PAT scopes)
- Rate limiting differentiation (stricter limits for PATs)
- Audit logging for sensitive endpoints

**Multi-tenancy considerations:**
- This pattern maintains multi-tenancy (still filters by user_id)
- No changes to row-level security
- IDOR protection remains unchanged
