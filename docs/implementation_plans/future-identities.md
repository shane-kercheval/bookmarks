# Future Identity Architecture: Internal Accounts + Linked External Identities

> **SUPERSEDED (2026-07-31, M6b decommission — migration plan AD2).** Written in the Auth0 era; the Auth0 → Clerk migration (see `2026-07-02-clerk-migration.md`) replaced the identity layer this plan reasons about. Clerk natively supports multiple linked login methods per user (account linking — see the ledger's account-linking entry), which absorbs this plan's core motivation. Retained as historical context only; the "internal account id + linked external identities" model, if ever needed beyond what Clerk provides, should be re-designed against the Clerk-era architecture.

## Context

The current model treats one Auth0 `sub` as one Tiddly account. That is acceptable for a PoC, but it is not a good long-term identity model:

- the same human can authenticate through multiple providers (`auth0` database, Google, Microsoft, GitHub)
- a provider-specific `sub` identifies one external login identity, not one human account
- email is useful profile/contact data, but it is not a safe canonical account key
- automatic account merging by email alone is unsafe

The target architecture is:

- `users.id` remains the canonical internal account ID used by bookmarks, notes, prompts, tokens, settings, consent, history, rate limiting, etc.
- a new `user_identities` table stores external login identities and maps many identities to one internal `users.id`
- account linking is explicit and proof-based
- same-email matches may be used to suggest linking, but never to auto-link

**Auth0 docs to read before implementing:**
- Account linking overview: https://auth0.com/docs/manage-users/user-accounts/user-account-linking
- Link user accounts: https://auth0.com/docs/manage-users/user-accounts/user-account-linking/link-user-accounts
- Verified email caveats: https://auth0.com/docs/manage-users/user-accounts/user-profiles/verified-email-usage
- Email verification: https://auth0.com/docs/manage-users/user-accounts/verify-emails
- Login flow / Actions: https://auth0.com/docs/customize/actions/flows-and-triggers/login-flow

## Architectural Decisions

1. **Tiddly account identity**
   - Canonical account ID is `users.id` (UUIDv7)
   - This is the only long-term user identifier clients and internal services should rely on

2. **External login identity**
   - Each Auth0 identity is stored in `user_identities`
   - Use the full Auth0 `sub` as the primary lookup key for authentication
   - Also store parsed provider metadata (`provider`, `provider_user_id`) for reporting/debugging, but do not use those as the primary auth lookup

3. **Email semantics**
   - Identity email belongs to the external identity and is stored on `user_identities`
   - `users.email` remains the account contact email for now
   - Do not overwrite `users.email` from every linked identity login once multiple identities exist

4. **Linking policy**
   - Never auto-link based only on matching email
   - Linking requires proof of control of both identities
   - Prefer app-managed linking in Tiddly, not Auth0 Management API account-linking as the system of record

5. **Backwards compatibility**
   - Not required
   - Prefer clean architecture over temporary compatibility layers
   - Remove legacy `users.auth0_id` usage once the new flow is complete

---

## Milestone 1: Database Identity Model

### Goal & Outcome

- The database supports one internal account with many external login identities
- Existing account-scoped tables continue to use `users.id`
- The schema is ready for auth lookup migration without relying on `users.auth0_id`

### Implementation Outline

1. **Add `user_identities` table**
   - Create a new model, e.g. `models/user_identity.py`
   - Recommended fields:
     - `id` UUIDv7 PK
     - `user_id` FK to `users.id` with `ON DELETE CASCADE`
     - `auth0_sub` string, unique, indexed
     - `provider` string, indexed
     - `provider_user_id` string
     - `email` nullable string
     - `email_verified` nullable boolean
     - `is_primary` boolean, default `false`
     - `created_at`
     - `updated_at`
     - `last_login_at` nullable timestamp
   - Add a uniqueness constraint on `auth0_sub`
   - Add a uniqueness constraint that allows only one primary identity per user. This can be a partial unique index on `(user_id)` where `is_primary = true` if supported in the current migration/database setup.

2. **Add ORM relationships**
   - `User.identities` one-to-many
   - `UserIdentity.user` many-to-one

3. **Keep `users.auth0_id` temporarily during migration**
   - Do not remove it yet in this milestone
   - It will be backfilled into `user_identities` and removed later

4. **Migration workflow**
   - **Never create migration files manually**
   - Update models first
   - Generate migrations only via:
     ```bash
     make migration message="add user identities table"
     ```
   - If a follow-up schema adjustment is needed, generate a second migration with `make migration`, do not hand-author migration files

5. **Data migration / backfill**
   - Add a backfill path that creates exactly one `user_identities` row for every existing `users` row using:
     - `auth0_sub = users.auth0_id`
     - `provider` derived from the prefix before `|`
     - `provider_user_id` derived from the suffix after `|`
     - `email = users.email`
     - `email_verified = users.email_verified`
     - `is_primary = true`
   - The migration/backfill must be idempotent or carefully structured so it can be run once safely in non-empty environments

6. **Documentation updates**
   - Add/update a short architecture doc or README section describing:
     - `users.id` is the account ID
     - `user_identities.auth0_sub` is the external login key
     - one account may have many identities

### Testing Strategy

- Model tests:
  - creating one user with one identity works
  - multiple identities can belong to the same user
  - duplicate `auth0_sub` is rejected
  - two primary identities for one user are rejected
- Migration tests:
  - existing users are backfilled to one primary identity
  - `provider` / `provider_user_id` parsing works for `auth0|...`, `google-oauth2|...`, etc.
  - rollback is not required if your migration policy does not support it, but upgrade behavior must be well tested
- Relationship tests:
  - deleting a user cascades to identities

**Stop for review after this milestone.**

---

## Milestone 2: Auth Resolution and User Provisioning

### Goal & Outcome

- Authentication resolves users through `user_identities.auth0_sub`, not `users.auth0_id`
- First login creates a new account plus its first identity
- Existing linked identities sign in to the correct account regardless of provider
- Identity-level profile data (`email`, `email_verified`, `last_login_at`) is synced on login

### Implementation Outline

1. **Add identity service layer**
   - Create a focused service module for:
     - parsing Auth0 `sub`
     - looking up identity by `auth0_sub`
     - creating a first identity for a new user
     - syncing identity profile fields on login
   - Keep auth resolution logic out of the `User` model

2. **Replace `get_or_create_user(db, auth0_id=...)` flow**
   - Current logic in `core/auth.py` should move from `users.auth0_id` lookup to `user_identities.auth0_sub`
   - New flow:
     ```python
     identity = await get_identity_by_sub(db, auth0_sub)
     if identity:
         sync_identity(identity, ...)
         return identity.user

     user = await create_user_with_defaults(...)
     await create_identity(
         db,
         user_id=user.id,
         auth0_sub=auth0_sub,
         provider=provider,
         provider_user_id=provider_user_id,
         email=email,
         email_verified=email_verified,
         is_primary=True,
     )
     return user
     ```

3. **Sub parsing**
   - Parse `sub` once in a small helper
   - Preserve the full `sub` string as the canonical external identity key
   - Derive:
     - `provider` = prefix before first `|`
     - `provider_user_id` = remainder after first `|`
   - Do not depend on provider-specific assumptions beyond this parse

4. **Identity profile sync policy**
   - On every login, sync `user_identities.email`, `user_identities.email_verified`, `last_login_at`
   - For `users.email`:
     - set it on first account creation
     - if the account has exactly one identity, keep syncing from that identity
     - once the account has multiple identities, do not implicitly change `users.email`
   - This keeps current product behavior sane without over-designing full contact-email management now

5. **Auth cache changes**
   - Keep caching by `users.id`
   - Replace cache lookups keyed by `auth0_id` with cache lookups keyed by `auth0_sub`
   - Rename cache helpers/keys if necessary so the code reflects the new abstraction cleanly

6. **Remove legacy `users.auth0_id` usage**
   - Once auth resolution and tests pass against `user_identities`, remove runtime dependence on `users.auth0_id`
   - Decide whether to drop the column in Milestone 2 or Milestone 5; do not keep dual-lookup logic longer than necessary

7. **Documentation updates**
   - Update auth flow documentation and comments in `core/auth.py`
   - Document how first-login provisioning now works

### Testing Strategy

- Unit tests:
  - existing identity resolves to the correct user
  - first login creates one user + one identity
  - repeated login through the same `sub` does not create duplicates
  - `provider` / `provider_user_id` parsing behaves correctly
  - identity email/email_verified sync updates the identity record
  - `users.email` sync behavior follows the single-identity vs multi-identity rule
- Integration tests:
  - first request populates auth cache using the new identity lookup path
  - second request hits cache and returns the same user
  - PAT auth still resolves by `users.id` and is unaffected
- Error tests:
  - malformed or missing `sub` still returns 401
  - race conditions on first login do not create duplicate users or identities

**Stop for review after this milestone.**

---

## Milestone 3: Explicit Identity Linking and Unlinking

### Goal & Outcome

- A logged-in user can explicitly link a second login method to the same Tiddly account
- The system requires proof of both identities before linking
- Future logins through any linked method resolve to the same `users.id`
- Users cannot accidentally lock themselves out by removing their only login method

### Implementation Outline

1. **Create account identity management API**
   - Add endpoints under a focused router, for example:
     - `GET /account/identities`
     - `POST /account/identities/link/start`
     - `POST /account/identities/link/complete`
     - `POST /account/identities/{identity_id}/set-primary`
     - `DELETE /account/identities/{identity_id}`
   - Naming can follow repo conventions, but keep the API explicit and account-scoped

2. **Recommended linking flow**
   - User is already authenticated to account A
   - User chooses “Link Google”, “Link Microsoft”, etc.
   - Frontend sends the user through Auth0 for the new provider
   - Backend validates the returned JWT and checks:
     - candidate `auth0_sub` is not already linked to another user
     - candidate `auth0_sub` is not already linked to the current user
   - If valid, create a new `user_identities` row for the current `users.id`

3. **Use short-lived server-side link state**
   - Use Redis or another server-side ephemeral store for the “link start” nonce/state
   - Do not trust only frontend state/query params for account-link operations
   - Store:
     - current `user_id`
     - requested provider
     - expiration time
     - CSRF/nonce values if needed

4. **Primary identity policy**
   - First identity created for a user is primary
   - Linking a new identity does not auto-promote it
   - Allow explicit promotion via API/UI
   - Prevent removing the last identity on an account

5. **Unlink policy**
   - Allow unlink only when the account still has at least one remaining login method
   - Prevent unlink if the target identity is the only identity
   - If unlinking the primary identity, require setting a different primary identity first or do it transactionally during the same action

6. **Do not use Auth0 account-linking as the source of truth**
   - Auth0 may still be used for authentication and provider orchestration
   - Tiddly should own the identity graph in its own database
   - Avoid coupling account ownership to Auth0 primary/secondary linked profile semantics

7. **Frontend/UI**
   - Add an account identities section in Settings
   - Show linked providers, email, verification status, primary badge, and last used timestamp
   - Add explicit “Link provider” and “Remove” actions

8. **Documentation updates**
   - Update settings/account docs
   - Document the explicit-link flow for future maintainers

### Testing Strategy

- API tests:
  - list identities for current account
  - linking a new provider to the current user succeeds
  - linking an identity already linked to another account fails
  - linking an already-linked identity to the same account is idempotent or returns a clear error
  - setting primary identity works and preserves one-primary-per-user invariant
  - deleting the last identity is rejected
- Integration tests:
  - linked Google and DB identities both authenticate to the same `users.id`
  - auth cache remains correct after linking/unlinking and primary changes
- UI tests:
  - linked identities render correctly
  - destructive actions show the right disabled/error states

**Stop for review after this milestone.**

---

## Milestone 4: Same-Email Link Suggestion Flow

### Goal & Outcome

- When a user logs in with a new identity whose **verified email** matches an existing account, the app suggests linking instead of silently auto-merging
- The user can either:
  - prove control of the existing account and link
  - explicitly create a separate account
- The system never auto-links based only on email

### Implementation Outline

1. **Add an auth-resolution decision point**
   - The current “auth dependency creates user on first authenticated request” flow is too implicit for this case
   - Introduce a dedicated post-login resolution endpoint or equivalent backend decision path that can return:
     - `authenticated_existing_account`
     - `new_account_created`
     - `link_suggested`

2. **Matching policy**
   - Only consider link suggestions when:
     - the incoming identity is unlinked
     - it has `email_verified = true`
     - it matches exactly one existing candidate account
   - Candidate matching should prefer identity email matches first; fall back to `users.email` only if needed and documented
   - Do not suggest linking for missing/unverified emails

3. **Pending decision state**
   - Use Redis or another short-lived server-side store to keep pending identity-resolution state
   - Store:
     - candidate `auth0_sub`
     - candidate provider/email info
     - matched `user_id`
     - expiration time

4. **User choices**
   - **Link existing account**
     - Require the user to authenticate with the existing login method
     - On success, link the candidate identity to that `users.id`
   - **Create separate account**
     - Create a new `users` row and link the candidate identity there
   - Do not create a new account automatically until the user chooses

5. **Frontend/UI**
   - Add a post-login interstitial for “We found an existing account”
   - Clearly explain:
     - why the app is asking
     - that the app found a verified-email match
     - that linking requires confirming the existing login method

6. **Documentation updates**
   - Document the suggestion flow and why matching email does not auto-merge accounts

### Testing Strategy

- Unit tests:
  - verified email + single account match -> `link_suggested`
  - unverified email -> no link suggestion
  - no email -> no link suggestion
  - multiple possible matches -> no auto-suggestion; require a safe fallback path
- Integration tests:
  - suggested-link flow completes successfully after proof of both identities
  - user can choose “create separate account”
  - no duplicate identities or accounts are created during retries/races
- UI tests:
  - interstitial renders correct choices and messaging

**Stop for review after this milestone.**

---

## Milestone 5: Legacy Cleanup and Final Migration

### Goal & Outcome

- Legacy `users.auth0_id` is removed from the schema and codebase
- All auth/account logic now uses `users.id` + `user_identities`
- The codebase no longer carries PoC-era identity assumptions

### Implementation Outline

1. **Remove `users.auth0_id` column**
   - Only after Milestones 1-4 are complete and reviewed
   - Update the `User` model and all references
   - Generate the migration with:
     ```bash
     make migration message="drop users auth0 id"
     ```

2. **Remove legacy code paths**
   - Delete old helpers, comments, tests, and cache naming that still reference `auth0_id` where the concept is now `auth0_sub` / identity
   - Keep code terminology aligned with the new model

3. **API cleanup**
   - Confirm `/users/me` and related account endpoints expose only app-level concepts
   - Do not leak Auth0-specific identifiers in long-term API contracts unless there is a concrete product need

4. **Documentation updates**
   - Update all auth and data model docs to remove `users.auth0_id`
   - Add a final architecture summary

### Testing Strategy

- Migration tests:
  - dropping `users.auth0_id` succeeds after backfill and lookup migration
- Regression tests:
  - full auth flow still works for existing and newly linked identities
  - PAT auth still works
  - settings/account identity management still works
- Search-based verification:
  - no remaining runtime references to `users.auth0_id` except in historical migrations/tests that intentionally preserve history

**Stop for review after this milestone.**

---

## What This Plan Intentionally Does Not Do

- It does **not** make email the canonical account key
- It does **not** auto-link accounts based on matching email
- It does **not** require Auth0 Management API account-linking as part of the core architecture
- It does **not** redesign marketing/contact email management beyond the minimal policy needed to avoid bad implicit overwrites

## Questions To Confirm Before Implementation

1. **Rename `users.email` now or later?**
   - Recommended clean model: rename to `contact_email` in this initiative
   - Lower-risk implementation: keep `users.email` for now and document that it means account contact email

2. **Include Milestone 4 in this initiative or defer it?**
   - Milestones 1-3 are the core architecture and explicit linking flow
   - Milestone 4 improves UX but adds meaningful post-login flow complexity

3. **Do you want unlinking in the first release of identity management?**
   - Recommended: yes, but with strict guardrails
   - If you want to reduce scope, linking can ship before unlinking
