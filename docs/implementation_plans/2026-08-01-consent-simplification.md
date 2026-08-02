# Consent simplification: move initial acceptance to Clerk, retire the blocking re-consent gate

**Status**: planned 2026-08-01. Supersedes nothing; closes ledger question 17.

## Why

Tiddly enforces policy acceptance with a blocking gate on every authenticated API surface: `_check_consent` in `core/auth.py` compares the user's stored `privacy_policy_version` / `terms_of_service_version` against the constants in `core/policy_versions.py` and raises HTTP 451 on any mismatch. Three clients carry bespoke 451-handling code to make that survivable, and a fourth (iOS) would have to add it.

That design conflates two different things. Accepting Terms of Service is **contract formation** — ordinary contract law — and changes to a contract are governed by the change-of-terms clause inside it, which both of Tiddly's policy documents already carry. GDPR **consent** is something else: a lawful basis for processing personal data, and not the basis Tiddly relies on for core service delivery (that is contract necessity — the data is processed to deliver the service the user signed up for). The gate treated a contract update as though it required fresh data-protection consent, and enforced it with the strictness the latter would demand. The July 2026 version bump that forced every user to re-accept was a third-party-processor disclosure change; the mechanism Tiddly's own terms specify for that is notice.

Nothing in this change affects the lawful basis for processing or the transparency obligation the published privacy policy satisfies.

Meanwhile Clerk has a first-class feature for the part that *is* worth keeping — capturing acceptance at account creation — enforced server-side at Clerk's API and rendered automatically by Clerk's own auth UI on web, the hosted Account Portal, and native iOS. Adopting it means initial consent is captured uniformly across **every current client, all of which use Clerk's prebuilt UI**, with no app code — and iOS never has to implement any of this. A future client that hand-builds its own sign-up screens would have to present the checkbox and pass `legalAccepted` itself, or Clerk rejects the sign-up; that constraint is Clerk's, not a gap in this design.

**The trade, stated plainly.** We give up: a per-version record of what each user accepted (Clerk stores one timestamp), IP/user-agent capture at acceptance time, and the ability to force acknowledgement of a materially adverse change. On the first — note that `user_consents` holds exactly **one row per user** and re-consent overwrites it in place, so it has never contained per-version history; what survives is a single row per user naming *the versions on that row* and the most recent acceptance date. The row proves acceptance of what it names, nothing more; it cannot reconstruct what someone accepted at an earlier version, and that was already true before this plan.

Note what M0 does to this on day one: it bumps both constants in the same PR, so the moment this merges *every* row names the superseded July 2026 versions while the documents in force are newer. No user has accepted the current documents in Tiddly's own records — the notice email is the entire basis, immediately, not eventually. That is the design working as intended rather than a defect, but it means the local record is one version behind from the start, and the paragraph above should not be read as promising otherwise. Going forward, dated policy-document history carries that role. The second was belt-and-suspenders on top of a required checkbox and a server-recorded timestamp. The third is a deliberate decision — if a genuinely material change ever lands (arbitration terms, a change in data use, training on user content), a web-only blocking modal gets built fresh at that time. The expensive part of what we are deleting is the cross-client 451 plumbing, not the version comparison.

**What replaces enforcement**: notice. On a policy version bump, the operator updates the documents, bumps the constants (which drive the public "Last Updated" date), and emails users. There is no transactional-email capability in the backend and this plan does not add one — at current scale the notice is a manual export-and-send, and M6 makes that obligation impossible to miss by putting the runbook next to the constants.

## Required reading before implementing

Read these first. Several decisions below depend on details that are not recoverable from the codebase.

- Clerk legal compliance (the instance setting): https://clerk.com/docs/guides/secure/legal-compliance
- Clerk custom flow for legal acceptance (`legalAccepted`): https://clerk.com/docs/guides/development/custom-flows/authentication/legal-acceptance
- Clerk iOS authentication flows: https://clerk.com/docs/ios/reference/native-mobile/auth
- Clerk Backend API `updateUser` (`legal_accepted_at`, RFC3339): https://clerk.com/docs/reference/backend/user/update-user
- Clerk Backend User object (`legalAcceptedAt`): https://clerk.com/docs/reference/backend/types/backend-user
- Known issue — SSO-initiated sign-up fails when legal compliance is enabled: https://github.com/clerk/javascript/issues/8338

Repo context: `docs/architecture.md` §5 (authentication, consent, request identity), `docs/auth0-clerk-ledger.md` (question 17 is the question this plan answers), and `clerk/README.md` for the config-as-code workflow, drift check, and dev→production promotion.

## How this ships

**The entire plan lands as one PR.** Milestones are implementation and review structure, not deploy boundaries.

**One merge is not one deploy.** `api` and `frontend` are separate Railway services (`README_DEPLOY.md` §Architecture), each built independently, each gated on "Wait for CI," with `api` additionally running `alembic upgrade head` before it starts. They go live minutes apart in an order nobody controls. If `api` lands first, page loads during the window fetch the old bundle, which calls the deleted `GET /consent/status`, gets a 404, and renders `AppLayout`'s full-screen "Unable to Load" panel — and its "Try Again" button re-calls the same missing endpoint, so it does not recover until `frontend` catches up.

**This window is accepted, not mitigated** — decided 2026-08-01. At current scale the exposure is a few minutes in which a handful of users might need to wait and reload. The alternatives were a temporary `/consent/status` stub (order-independent, but leaves a dead endpoint and a mandatory follow-up PR) or operator-sequenced deploys (pause `api` auto-deploy, merge, wait for `frontend`, release `api`). Both were judged more machinery than the risk warrants. Recorded here so it is legible as a decision rather than an oversight; if the userbase grows materially, revisit before a comparable change.

The ordering that does matter is operator-side, because those steps are not code and do not ride the merge:

1. **Clerk legal consent enabled and verified in production** — must precede the merge. Otherwise the merge removes the gate while nothing has begun capturing acceptance, and any account created in that window has no record in either system.
2. **Merge** — deploys the gate removal across both services simultaneously.
3. **Backfill run** — any time after. It is record-keeping; nothing enforces the field.
4. **Email notice for the privacy-policy correction (M0)** — after the merge publishes the corrected document, so the link people follow shows the new text.
5. **Delete the backfill script and its tests** — after the production run, since the script cannot run again meaningfully. `backend/scripts/clerk_legal_backfill.py` and `backend/tests/scripts/test_clerk_legal_backfill.py` go together in one commit. Until then the tests run on every `make backend-verify` and every CI run (0.06s; the cost is conceptual, not runtime), which is accepted so the classification logic stays reviewable while it still matters — checking in an unreviewable script that writes to production would be the worse trade.

   **When deleting, record the commit SHA in the ledger.** The M6a import script was deleted the same way and nothing pointed at it afterwards, so this plan had to recover it with `git show 9a7f3a3^:backend/scripts/clerk_import.py` to copy its conventions. That has now happened twice. If `backend/tests/scripts/` ends up holding only `__init__.py` and `conftest.py` again, delete those too — they were left orphaned by the M6a sweep and served nothing until this milestone arrived.

Production Clerk changes require per-change approval from the user. Rehearse on the dev instance, present the production command set, and wait.

## Out of scope

Do not build: a transactional email capability, an in-app notification surface, a replacement blocking mechanism, or any abstraction for "future consent types." Do not delete the `user_consents` table or its data. Do not adopt Clerk API Keys (a separate, still-open question).

---

## M0 — Correct the factual drift in both policy documents

### Goal & Outcome

The published Privacy Policy and Terms of Service describe the service that actually exists and the AI processing that actually happens, so the acceptance Clerk starts capturing is acceptance of accurate documents.

- Both documents describe the product as it is: bookmarks, notes, **and prompt templates**.
- The AI features are described as live, with the providers content is actually sent to and what is actually sent.
- The "Future AI Services (Not Yet Implemented)" framing is gone from both documents.
- Both version constants advance and the change goes out by email — the first exercise of the notice mechanism this plan establishes.

### Implementation Outline

Found during review, not part of the original scope. Scope was widened once more during the implementation review (2026-08-01): the original draft corrected only the privacy policy's AI section, but Clerk's checkbox asks new users to affirmatively accept **both** documents, and the Terms carry the same class of error. Shipping a knowingly-false Terms under an affirmative-acceptance regime is the exact defect M0 exists to fix, in the other file.

The drift, all verified against the code:

**Privacy Policy** (`frontend/src/content/prose/privacy.md`):

- `:79-93` is headed **"Future AI Services (Not Yet Implemented)"**, states the features "are not yet available", and names only OpenAI and Anthropic as prospective processors.
- `:20` lists stored data as "**Bookmark Data:** URLs, titles, descriptions, and page content" — notes and prompt templates are absent from the document entirely.

**Terms of Service** (`frontend/src/content/prose/terms.md`):

- `:15` — "Tiddly is a bookmark management application… save, organize, and search bookmarks." No notes, no prompt templates.
- `:110` — the third-party services list carries "**Future AI services** (when implemented, subject to their terms)".

The corrections the prose must make:

- **The features are live and user-initiated.** Five endpoints under `/ai/*` — tag suggestions, metadata suggestions, relationship suggestions, and two prompt-argument suggestion endpoints — each invoked by an explicit user action, not background processing.
- **Three providers, not two.** OpenAI, Anthropic, and Google (Gemini), reached through LiteLLM (`services/llm_service.py:66-79`). The platform default for suggestions is an OpenAI model. Each needs its own entry in the third-party processor list with a link to its privacy policy, matching the format of the existing Clerk and Railway entries.
- **What is sent is broader than "the item being processed"** — an earlier draft of this plan said exactly that and was wrong. Verified against `services/llm_prompts.py`: tag suggestions also send up to 100 of the user's existing tag names *with their usage counts* (`:60-63`); relationship suggestions also send candidate items' titles, descriptions, and up to 1000 characters of content preview each (`:213-221`); the prompt-argument endpoints send the full template body (`:298-302`). The disclosure must cover data *related to* the item, not only the item.
- **BYOK keys are not stored.** A user-supplied provider key travels per-request in the `X-LLM-Api-Key` header and is never persisted server-side. This is a genuinely favourable fact the current policy doesn't get to state.
- **Do not assert anything about provider training or retention.** API-tier defaults differ by provider and change over time; link each provider's policy rather than making a claim on their behalf. If a stronger statement is wanted later, verify it first.

**The fee sections stay as they are** — checked and deliberately not changed. `terms.md:123-127` says the service is free during beta and pricing "may be introduced in the future". That is *true*: Clerk billing is off (`billing.user_enabled: false`, `plans: {}`), there is no payment integration in the codebase, and `users.tier` has no self-serve upgrade path. `tiers.json` publishing $2/$5 on the Pricing page is prospective pricing stated precisely in one place and vaguely in another — a specificity mismatch, not a false statement. Correcting it would mean authoring fee terms for a billing system that does not exist.

Edit the markdown source in `frontend/src/content/prose/`, not the `.tsx` renderers.

Bump **both** `PRIVACY_POLICY_VERSION` and `TERMS_OF_SERVICE_VERSION` in `core/policy_versions.py` with a comment recording what changed and why, following the convention the July 2026 entry set. Because the consent gate is removed in this same PR, no user is prompted to re-accept; the notice goes out by email per the M6 runbook, which makes this its first real use — and covers both documents.

Two notes for the operator, neither blocking:

- Between production Clerk enablement (M1) and the merge that publishes the corrected prose, the checkbox links to the uncorrected policy. Consistent with the deploy-window decision above; noted rather than sequenced around.
- While verifying, the rights-request contact at `privacy.md:104` was observed to be a personal email address. Out of scope here, flagged for the user's judgment.

**The prose is legal content and ships only after the user reviews the wording.** The agent drafts against the facts above; it does not decide the language unilaterally.

### Definition of Done

Both documents describe bookmarks, notes, and prompt templates. The AI sections reflect live behavior with all three providers listed as processors and a data description that covers the related data actually sent. Both version constants bumped with rationale. `frontend/src/content/proseDocs.test.tsx` (frontmatter completeness + route coverage for `/privacy` and `/terms`) still passes. The email notice is an operator step recorded alongside the M1/M2 operator actions.

---

## M1 — Enable legal consent on the Clerk instances

### Goal & Outcome

Clerk becomes the capture point for initial policy acceptance, on every sign-up path.

- A new user cannot create an account on any Clerk surface — hosted Account Portal, the web app, or the native iOS app — without affirmatively accepting the Privacy Policy and Terms of Service.
- Acceptance is recorded by Clerk as `legalAcceptedAt` on the user.
- The links in the acceptance checkbox resolve to Tiddly's published policy pages.
- Google (SSO) sign-up is confirmed to work with the setting enabled, not assumed to.

### Implementation Outline

This is a config-as-code change, not a dashboard hunt: `clerk/config.dev.json` already contains `compliance.legal_consent` with `enabled: false` and both URLs null. Set `enabled` true and populate `privacy_policy_url` and `terms_of_service_url` with Tiddly's published pages, and apply to the dev instance.

**Promote to production with a targeted patch, never a whole-file put.** `clerk/README.md:46-51` documents `clerk deploy` (clones dev → prod) and `clerk config put --instance prod --file clerk/config.dev.json` as whole-instance operations, and states that production-specific values that differ from dev — the real Google OAuth credentials and the production Frontend API domain — "are applied on top and are **not** in this file." Either command would therefore revert those to dev values and break production sign-in. Use `clerk config patch --instance prod` scoped to `compliance.legal_consent` alone, and capture a `clerk config pull --instance prod` diff before and after as the verification artifact — the evidence discipline the ledger uses elsewhere. If a targeted patch turns out not to reach this setting, stop and bring it back rather than working around it by reapplying overrides by hand.

Client-side expectations, both established rather than assumed:

- **Web** uses Clerk's own components and hosted portal (`@clerk/clerk-react`'s `SignIn` in `SessionExpiredDialog.tsx`, `ClerkProvider`/`useClerk` in `AuthProvider.tsx`, `UserProfile` in settings) with no hand-built sign-up form. The checkbox renders automatically; no frontend change.
- **iOS** uses Clerk's prebuilt auth UI — confirmed 2026-08-01 with the iOS engineer. The checkbox renders automatically there too; no app change. This matters because Clerk enforces the requirement server-side: a hand-built sign-up form that doesn't send `legalAccepted` would fail the API call, so the prebuilt-UI answer is what makes "no app code" true rather than merely hoped for.

**No iOS smoke test is required** — decided 2026-08-01. The design question is answered by the confirmation above, the userbase is small, and the worst case is a fixable break in native sign-up that the iOS owner ships an update for. Gating this work on a cross-repo manual test buys little at this scale. Recorded so it isn't re-opened as an oversight. If a custom flow ever does become necessary on any client, the checkbox must be a real user affirmation — passing `legalAccepted: true` unconditionally to silence the error is not an acceptable resolution.

Then verify on the dev instance, in a real browser — not by inspecting configuration:

1. Email/password (or email-code) sign-up shows the checkbox, refuses to proceed without it, and produces a user whose `legalAcceptedAt` is populated (read it back via `clerk api`).
2. **Google sign-up initiated from the sign-in page.** This is the specific path issue #8338 describes: when a sign-in-initiated SSO flow turns out to belong to a new user, Clerk converts it to a sign-up that now requires `legalAccepted`, and the flow can fail at complete-sign-up. The failure mode is a broken onboarding path, not a consent bypass. If it reproduces, record the exact symptom and stop — the rest of the plan is still sound, but this becomes a blocker for production enablement, and the resolution (SDK version, a custom flow, or waiting on an upstream fix) is the user's decision, not the implementing agent's.
Record the outcomes in the ledger's question 17 entry with the date and that file's provenance convention (exercised vs. documented) — noting that iOS rests on the owner's confirmation, not on an exercised test.

### Definition of Done

Both browser sign-up paths verified live on the dev instance with the outcomes written down. `clerk/config.dev.json` change committed. Production enablement prepared and, once approved and executed, verified before the PR merges — see *How this ships*. Ledger question 17 updated.

---

## M2 — Backfill `legal_accepted_at` in Clerk from existing consent records

### Goal & Outcome

Clerk's acceptance field means "has accepted the terms" rather than "signed up after we flipped the toggle."

- Every existing user with a `user_consents` row and no Clerk acceptance timestamp has `legalAcceptedAt` populated from Tiddly's record.
- Users who already have a Clerk timestamp keep it; the script never overwrites one.
- Users with no consent record are left null, which is the accurate representation.
- The script is idempotent and reports what it did, so it can be dry-run, reviewed, and re-run.

### Implementation Outline

A one-time script reading from Postgres and writing to Clerk. Source is `user_consents.consented_at`; destination is `legal_accepted_at` on the Clerk user via the Backend API `updateUser`, in RFC3339. The join key is `users.external_auth_id`, which since the M6b decommission migration *is* the Clerk user ID (non-nullable).

**Write only when the destination is null.** Once M1 is live, a user can hold a genuine Clerk sign-up timestamp; `user_consents.consented_at` is the *latest* acceptance Tiddly recorded, not the original, so copying over a populated field would replace the better record with the worse one. When the destination is non-null, classify it as already-populated and report whether the values agree or differ — never overwrite automatically. Name the source semantics accordingly throughout: "latest acceptance recorded by Tiddly," not "original acceptance."

Preserve that timestamp rather than writing `now` — writing the backfill date would destroy the only record of when acceptance happened and make the field actively misleading.

The dry-run report must include: total rows selected, the distribution of `consented_at` (so the cohort shape is on the record), the count of already-populated destinations split by agree/differ, **the count of users with no `user_consents` row at all**, and **the split between rows naming current policy versions and rows naming stale ones**. Both of those last two are cohorts that are blocked today and have never accepted the current documents — the operator needs the whole picture, not half of it. See Known limitations.

Follow the conventions of the M6a Clerk import script, which was deleted in the Auth0 reference sweep and is retrievable at `git show 9a7f3a3^:backend/scripts/clerk_import.py` (tests at `git show 9a7f3a3^:backend/tests/scripts/test_clerk_import.py`). Copy specifically: dry-run as the default mode, hard-fail preflight classification rather than silent skips, and a required explicit `--database-url` so the script cannot write against whatever the local environment happens to point at. `clerk-backend-api` is still a live dependency, so the SDK usage transfers unchanged.

Two operational rules carried from the M6a experience, both of which cost real debugging time then:

- After an ambiguous write failure, confirm state by reading the user back rather than inferring success or failure from the call's result.
- Hard-fail on rows that cannot be matched to a live Clerk user rather than skipping them. That is a finding needing an operator decision, not a warning to scroll past.

Rehearse against the dev instance. Production execution is an operator step requiring approval.

### Definition of Done

Dry-run and wet-run exercised on dev, including a re-run proving idempotency, and the unmatched-row hard-fail exercised by seeding a row that cannot resolve.

Tests cover the decision logic without requiring a live Clerk instance: all three destination states (null → writes; equal → reports, no write; differing → reports, no write), timestamp formatting, row selection, and the unmatched-row failure.

Production run prepared and held for approval; once executed, the result and the never-consented count recorded in the ledger, and the script plus its tests deleted per step 5 of *How this ships*.

---

## M3 — Retire the consent gate in the backend

### Goal & Outcome

The backend stops enforcing policy acceptance. This is the core deletion and the highest-risk milestone, because it edits the authentication path.

- Authenticated requests succeed regardless of whether the user has a consent record or which versions it names. No endpoint returns HTTP 451.
- The published API contract stops advertising a consent error and a consent endpoint that no longer exist.
- The public policy pages still get their "Last Updated" date — `GET /consent/versions` and `core/policy_versions.py` survive unchanged.
- The `user_consents` table and its data survive as a frozen historical record, still cascade-deleted with the user.
- The auth cache no longer carries consent fields, and stale entries in the old shape are unreachable rather than misinterpreted.

### Implementation Outline

**Enforcement.** Delete `_check_consent` and the `CONSENT_INSTRUCTIONS` template from `core/auth.py`, and remove the call from `get_current_user`, `get_current_user_session_only`, and `get_current_user_ai`. Delete both consent-exempt dependency variants (`get_current_user_without_consent`, `get_current_user_session_only_without_consent`) and their re-exports from `api/dependencies.py` — their only consumer is the consent router itself, and the session-only variant already has none. Once the gate is gone the distinction they exist to express no longer exists, so keeping them would leave two names differing from their siblings in nothing.

Removing those two also requires updating `__all__` (`core/auth.py:57-58`) and the `AUTH_DEPENDENCIES` tuple near the bottom of the module. `tests/core/test_auth_dependency_invariant.py` asserts that tuple equals every discovered `get_current_user*` callable, so a miss fails loudly rather than silently — but omitting them entirely fails at import.

**Endpoints and schemas.** In `api/routers/consent.py`, delete `GET /consent/status` and `POST /consent/me`; **keep `GET /consent/versions`**, which is public, unauthenticated, and consumed by the Privacy Policy and Terms of Service pages. In `schemas/user_consent.py`, retain only `PolicyVersions`.

**Keep `core/request_utils.get_client_ip`**, even though the deleted accept-endpoint was its only caller. Its docstring is where the module's knowledge lives — the `X-Real-IP` precedence rationale, the Railway documentation citation, the explicit spoofability boundary, and a dated production confirmation (2026-06-21) that a forged header is overwritten at the edge, which is the written justification for trusting per-IP rate-limit keys. `resolve_client_ip`, which survives for abuse logging, documents itself by pointing at that docstring. Deleting the wrapper would orphan that cross-reference and destroy the evidence; it costs one line and `test_request_utils.py` already covers it.

**Delete `Settings.api_url` and `Settings.frontend_url`** (`core/config.py:60,64`). Their only readers are `CONSENT_INSTRUCTIONS` and its formatting call (`core/auth.py:127,630,631`), so after this milestone they are a false backend contract — configuration operators maintain that affects nothing. Remove their assignments from the auth test setup, and drop `VITE_FRONTEND_URL` from the backend/API sections of `.env.example` and `README_DEPLOY.md`. Leave `VITE_API_URL` alone where the frontend and MCP services use it independently.

**The published API contract.** These surfaces advertise consent behavior to machine clients and would otherwise keep describing unreachable behavior forever; nothing in `make backend-verify` catches documentation that lies. Remove:

- `schemas/ai.py` — `ConsentDetail` and `ConsentRequiredResponse` (~lines 66–128, including a `consent_url: "/consent/status"` example) and the 451 reference in the module docstring (~line 42).
- `api/routers/ai.py` — the `ConsentRequiredResponse` import (line 21), the `451:` entry in `_BASE_AI_ERROR_RESPONSES` (lines 108–114), and the consent mentions at lines 335 and 651.
- `api/main.py:185-187` — the app-level description calling out 451 as one of two special error shapes.
- `core/config.py:59` — the comment attributing `api_url`/`frontend_url` to consent messages. Only the comment is certainly stale; check for non-consent consumers before touching the settings themselves.

**Cache.** Remove `consent_privacy_version` and `consent_tos_version` from `CachedUser`, and **bump `CACHE_SCHEMA_VERSION` from 7 to 8** in `core/auth_cache.py`. The class docstring states this requirement and the reason: version-in-key makes old entries unaddressable by construction, so a running deployment cannot deserialize the previous shape. Remove the consent-driven cache invalidation the deleted accept-endpoint performed; leave email-change invalidation intact.

The `joinedload(User.consent)` options on user-resolution queries exist to feed the gate. Remove them where that is their only purpose — read each call site, because at least one loads consent alongside other relationships.

**Keep**: `models/user_consent.py` and the table, the consent cascade in `services/user_service.py` and the deletion webhook, and `core/policy_versions.py`. Add a docstring note on `UserConsent` recording that it is a frozen historical record as of this change — nothing writes to it anymore — so a future reader does not mistake it for a live system.

**No Alembic migration.** Nothing about the database schema changes: no table dropped, no column added or altered. Say so in the commit message; the previous decommission cycle raised exactly this question.

The `DEV_MODE` consent bypass disappears with the gate it bypassed.

**One test must survive the sweep.** `tests/core/test_auth_clerk.py:851` — `test__freshly_created_user_not_cached_until_committed` — matches "consent-related assertions" by description but is the regression test for the phantom-cache 500, a bug that already shipped once. Its docstring frames the rollback trigger as the consent gate 451-ing a brand-new user's first request; so does the source comment at `core/auth.py:429-436` that justifies the `if created: return user` guard. **Keep the test and reword both**, re-justifying against a rollback path that survives — rate-limit rejection is the cleanest, since `_apply_rate_limit` raises after user creation and rolls back the same first-request-created row. If the guard's only written justification is deleted along with the gate, a later reader has no stated reason not to remove the guard. This intersects the deferred auth-cache post-commit-publication follow-up; cross-reference it so that work doesn't land on a comment that no longer explains itself.

### Definition of Done

Tests are deleted here because the behavior they cover is deleted, not to make anything pass. That is only legitimate if the coverage is *replaced*, so the deletion must be paired with new assertions.

Consent is currently enforced on three distinct auth families — standard, session-only, and AI — so the replacement tests must exercise a representative endpoint from **each**, or a partial removal leaving the gate live on one family would pass the very tests meant to catch it:

- A user with **no** `user_consents` row successfully calls a previously-gated endpoint in each family.
- A user whose consent row names **stale** versions likewise succeeds in each family.
- `GET /consent/versions` still returns both current versions and requires no authentication.
- The existing cache schema-version test exercises the new v8 boundary.
- `test_auth_dependency_invariant.py` passes with the two removed variants gone from `AUTH_DEPENDENCIES`.

Then delete `backend/tests/test_consent.py` and the consent assertions in `tests/core/test_auth_clerk.py` (excepting the phantom-cache test above), `tests/core/test_auth_session_only.py`, `tests/integration/test_rate_limit_all_endpoints.py`, and the API suites. Simplify the consent-creating fixtures in `tests/conftest.py` and `tests/api/conftest.py` rather than leaving them writing rows nothing reads.

Update `backend/tests/security/deployed/test_live_penetration.py`, which asserts consent behavior against production. Per `AGENTS.md`, remind the user to run the deployed security tests after this ships.

`make backend-verify` green.

---

## M4 — Remove the consent dialog and 451 handling from the web app

### Goal & Outcome

The web app has no consent flow. A user signs in and uses the app; acceptance happened at sign-up, in Clerk.

- No consent dialog exists or can appear.
- Saving a shared public item while signed in works through a single path, with no consent-required branch.
- The Privacy Policy and Terms of Service pages still display their "Last Updated" date, fetched as they are today.

### Implementation Outline

Delete `components/ConsentDialog.tsx` and `stores/consentStore.ts` outright, with their tests. Remove the 451 branch from the axios response interceptor in `services/api.tsx:309-311` (its other status handling — 401, 402, 429 — is untouched), along with the now-dead consent API surface in the same file: the `ConsentResponse` / `ConsentCreate` / `ConsentStatus` types (~lines 74–95) and the `checkConsentStatus` / `recordMyConsent` functions (~lines 337, 346). Remove the dialog mounting and gating touchpoints in `AppLayout.tsx`, `App.tsx`, `Layout.tsx`, and `AuthProvider.tsx`.

Three components have 451-aware branches in the "save a shared item" path — `hooks/useSavePublicItem.ts`, `pages/SaveSharedRedirect.tsx`, and `components/SaveACopy.tsx`. These exist because a signed-in-but-unconsented user hitting a save action needed 451 treated as a non-failure that hands off to the dialog. That case no longer exists, so each collapses to a single success/failure path. Read the surrounding comments before cutting: they explain a redirect interaction that is easy to break by deleting one branch too many.

`stores/sessionExpiryStore.ts` mentions consent only in a comment describing what deliberate logout resets; update the comment to match reality.

Leave `pages/PrivacyPolicy.tsx` and `pages/TermsOfService.tsx` alone apart from anything referencing the removed store — they fetch `/consent/versions`, which survives.

Update the `searchText` entry in `data/docsRoutes.tsx` if it indexes consent-flow terms that no longer describe anything, per the command-palette obligation in `AGENTS.md`.

### Definition of Done

Deleted tests: `ConsentDialog.test.tsx`, `consentStore.test.ts`, and the consent assertions in `AppLayout.test.tsx`, `AuthProvider.test.tsx`, `Layout.test.tsx`, and `api.test.ts`.

Replacement coverage matched to risk — the save-shared-item path is the only place where deleting a branch can silently change behavior, so `useSavePublicItem.test.tsx` and `SaveSharedRedirect.test.tsx` must still assert the success and failure paths including the redirect. Everything else here is straight deletion and needs no new test.

`make frontend-verify` green. Per the standing preference, do not run backend tests for this milestone.

---

## M5 — Remove 451 handling from the CLI and Chrome extension

Small and mechanical; compressed accordingly.

### Goal & Outcome

Neither client carries dead consent-handling code, and neither can present a consent message that no longer corresponds to anything.

- `tiddly login` completes without a consent branch.
- MCP configuration's token validation treats a working token as working, with no special case.
- The extension popup has no consent-required state.

### Implementation Outline

**CLI**: remove the `case 451` and `handle451` from `internal/api/client.go`, the consent fields on `APIError`, the post-login 451 branch in `cmd/login.go`, and the 451-accepting case in `internal/mcp/configure.go` (which treated 451 as "the token works"). Clean up the corresponding fixtures in `internal/testutil/fixtures.go`.

`internal/auth/pkce_flow.go` matches a grep for "consent" because of the **OAuth authorization consent screen** — an unrelated concept. Leave it alone.

**Chrome extension**: remove the 451 branch in `popup-core.js`. The `build/` directories are generated artifacts, not sources.

### Definition of Done

`make cli-verify` green with the 451 test cases removed and no replacement needed — there is no behavior left to assert. Extension build test still passes; run `make chrome-ext-build` if the popup change affects the bundled artifact.

---

## M6 — The version-bump runbook

### Goal & Outcome

The notice mechanism that now replaces enforcement is written down where the person changing a policy version will actually see it.

- Anyone bumping a policy version constant finds, at that spot, the full list of what else must happen.

### Implementation Outline

**No prose change is needed.** Both documents already carry the enabling language and the email commitment: `terms.md:185-191` lists the "Last Updated" date, a notice on the Service, and an email to the registered address, all scoped to material changes, and closes with continued use constituting acceptance; `privacy.md:131-137` says the same with email qualified inline. Record this in the plan so a future reader doesn't re-open the question — an earlier draft claimed a gap here that does not exist.

Add the runbook as a comment block in `core/policy_versions.py`, directly above the constants. The placement is the point: the constants are the trigger, so the obligation cannot be missed by someone who only touches that file. Ordered steps: update the prose in `frontend/src/content/prose/`, bump the constants (which drive the displayed "Last Updated" date), export current user emails **from Clerk** rather than from `users.email` (Clerk requires an email identifier so its list is complete; the local column is nullable), and send the notice.

Record there, in one line, why there is no automated mechanism: a deliberate scale-matched choice, not an oversight. Describe the notice as a service message about the terms governing the account — state the intent, not a legal conclusion about what unsubscribe machinery is or isn't required.

### Definition of Done

Runbook present at the constants. No prose edits. No new tests warranted.

---

## M7 — Documentation and close-out

### Goal & Outcome

The architecture documentation describes the system that now exists, and the open question this work answers is closed.

### Implementation Outline

`docs/architecture.md` carries the most consent detail and needs the most care. Known references: the store list (~105), the interceptor's status handling (~110), the auth-layer description (~183), all of §5 "Authentication, consent, and request identity" (~250–289, including the dependency table listing the two removed variants), the Redis key-schema table (~385, which names `auth:v7:` and must move to v8), and the error-code table (~442). Re-read §5 as a whole rather than patching lines — its narrative of the request lifecycle changes shape, and the "Things that are easy to miss" section is the right home for the note that `user_consents` is now a frozen historical table holding one latest-acceptance row per user.

Check `AGENTS.md`'s auth summary and update it if it describes consent enforcement.

**Do not change `frontend/public/llms-integration.txt`.** Its line 22 discusses the OAuth authorization consent screen for AI apps — a different concept this work does not touch. Verify the rest of the `llms*.txt` family for policy-consent references before concluding; a grep for "451" across `frontend/public/` currently returns nothing.

Close ledger question 17 following that file's marker convention (`[ANSWERED <date>]`, answer written into the relevant entry, inline markers removed). The honest answer is that Clerk's feature does *not* replace the system as it was — no version awareness, no re-consent trigger, no enforcement outside sign-up — and that the resolution was to change the requirement rather than seek a replacement for it. That framing is the useful part for the migration writeup.

### Definition of Done

`docs/architecture.md` §5 and every listed reference updated, including the Redis key-schema version. Ledger question 17 answered and its inline markers removed. A grep for consent-enforcement language across `docs/` and `frontend/public/` returns nothing stale.

---

## Known limitations, recorded deliberately

- **No per-version acceptance record, past or future.** `user_consents` holds one row per user, overwritten on each acceptance, so per-version history never existed. The surviving row proves acceptance of *the versions it names* — and since M0 bumps both constants in this same PR, from the merge onward that is never the current pair: every row names the superseded July 2026 versions. No existing user has accepted the corrected documents in Tiddly's records, and none will be asked to; the notice email is the whole mechanism from day one. Going forward, dated policy-document history carries the record-keeping role.
- **No IP or user-agent capture at acceptance.**
- **No forced acknowledgement of material changes.** If one ever lands, build a web-only blocking modal then. The version-comparison logic was never the expensive part.
- **JIT-created and API-created accounts bypass the checkbox.** Clerk's setting gates its sign-up ceremony; a user created through the Backend API with `skipLegalChecks` has no acceptance record. M2 closes the existing population; anything created outside sign-up afterwards is an operator responsibility.
- **Two cohorts get service without having accepted the current documents.** Users with no `user_consents` row at all, and users whose row names stale policy versions. Both are blocked today and both will get full service afterwards. By construction these can only be dormant accounts, and "continued use constitutes acceptance" is a weaker argument for someone who never accepted anything initially than for someone accepting an update. M2's dry-run reports both counts; if either is non-zero, the disposition is a decision to make with the numbers in hand.
- **A deploy window in which the web app is broken.** See *How this ships* — `api` and `frontend` deploy independently and minutes apart, and in one of the two orders the app renders a full-screen error that its own retry button cannot clear. Accepted deliberately at current scale rather than mitigated with a stub or operator-sequenced deploys. Separately and more narrowly, a browser tab left open across the deploy can hit the same error until reloaded.
- **The notice step is manual and unenforced.** M6 mitigates by placement, not by automation. This is the accepted cost of not building an email capability.
