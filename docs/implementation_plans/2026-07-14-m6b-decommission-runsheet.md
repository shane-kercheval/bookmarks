# M6b decommission run sheet (remove Auth0 entirely)

**Date**: 2026-07-14
**Status**: Proposed operational contract — in **PR #155** (companion to [`2026-07-14-m6a-cutover-runsheet.md`](2026-07-14-m6a-cutover-runsheet.md)). Reviewed now, **executed later** — M6b runs only after the dual-accept window closes (gated on the iOS app shipping); it is planned now so the one-way-door half is settled before M6a is considered fully planned.
**Governs**: Milestone 6, half B of [`2026-07-02-clerk-migration.md`](2026-07-02-clerk-migration.md) (Implementation Outline "M6b — decommission", steps 4–8).

---

## Why this is a separate, staged run sheet

M6b is the migration's **only one-way door**. The plan compresses code removal, schema change, env cleanup, cache change, and vendor-account deletion into one "decommission change-set." **Do not execute that as one irreversible deployment.** This sheet stages it **expand/contract**: ship Clerk-only *code* while the Auth0 column, config, and tenants still exist → verify in production with a rollback window → only then drop the column and transitional machinery → remove env vars once no deployed code needs them → **delete the Auth0 tenants last.** That preserves a real rollback path right up until the tenants are gone.

Legend (`[C]` / `[S]` / `[C→S]`) and the credential-custody rule are the same as the M6a sheet.

---

## Gate G — the window is actually closed (direct confirmation, not a monitored soak)

At this scale the decommission gate is a **direct confirmation with a known cohort**, not a log-watching wait. The log going quiet is a **backstop that should agree**, not the mechanism.

| # | Step | Who |
|---|------|-----|
| G1 | **Re-enumerate the cohort** at execution time (do not trust counts recorded earlier). Today: two iOS users (maintainer + app developer, both TestFlight) **plus any CLI users** surfaced during the M6a soak. | **[S]** |
| G2 | For **every** cohort member, on **every device they use**, confirm they have: installed/upgraded the Clerk build, launched it, **signed in through Clerk**, and made **one successful authenticated request** landing on their **existing** account. (Install alone is insufficient — removing Auth0 after install-only could kill the fallback while the Clerk path is silently broken for that user.) | **[S]** |
| G3 | **Backstop (also required, not merely advisory):** confirm the Auth0-path log (including `source=ios`) shows **no unexplained traffic**. G2 and G3 must **both** hold. A disagreement — a confirmed-migrated cohort but lingering Auth0-path traffic, or the reverse — means the gate is **unresolved**: stop and investigate until explained. Neither signal "wins." | **[C]** monitors + **[S]** resolves |

**Exit G:** every known Auth0 client confirmed on Clerk against their real account **and** the log shows no unexplained Auth0-path traffic; any disagreement resolved before proceeding.

---

## Phase H — Expand: deploy Clerk-only code, retain Auth0 column/config/tenants

Everything Auth0 stays *present but unused* here, so this deploy is revertible.

**H entry criterion (define the rollback window *before* starting H, not during it).** Phase H is the last rollback opportunity's evidence-gathering window. Set its minimum up front: at least **one complete normal-use cycle for both iOS users and every known CLI client, with zero Auth0-path traffic and zero Clerk errors observed**, before Phase I's contract begins. If that evidence isn't accruing, you extend H — you do not proceed to I on a timer.

| # | Step | Who |
|---|------|-----|
| H0 | **Fresh production DB snapshot** and a **final Auth0 bulk export**; assign the archived export a **named retention owner and period** (it contains every user's email). | **[S]** |
| H1 | **`external_auth_id IS NULL` preflight** on production (users are **hard-deleted**, not soft-deleted — there is **no `deleted_at` column**, so do not filter on one): `SELECT id, email, auth0_id FROM users WHERE external_auth_id IS NULL;`. **Every returned row blocks M6b** and is investigated/resolved before proceeding — not discovered as a failed migration later (the JIT-create flags existed precisely to keep this empty). Also run the identity reconciliation as explicit counts: `SELECT count(*) FROM users;` must equal `SELECT count(*) FROM users WHERE external_auth_id IS NOT NULL;`, and `SELECT count(*) FROM users WHERE auth0_id IS NOT NULL AND external_auth_id IS NULL;` must be **0**. **Window-signup reconciliation gate (closes M6a's waived-freeze residual):** confirm **zero** Auth0 identities with `created_at` after the M6a export cutoff — the recurring check the M6a run sheet committed to (M6a dropped the provider-edge sign-up freeze; a window-era Auth0 signup could exist as an unusable dangling identity). Any hit is resolved (delete from Auth0, record, direct the user to Clerk) before M6b proceeds. | **[C→S]** |
| H2 | **Deploy the Clerk-only application code**, but **retain** `auth0_id`, the Auth0 config/Settings fields/validators, and the tenants: remove the Auth0 verification branch + the issuer-routing Auth0 arm (unknown issuer → 401 stays); stop *using* the per-issuer JIT-create **branching logic** (single-issuer world). **The `auth0_jit_create_enabled` Settings *field* itself is removed later, in Ic** — leaving the config surface intact here keeps this deploy cleanly revertible. **Do NOT** drop the column, bump the cache schema, remove Settings fields, or delete env vars in this deploy. | **[C→S]** |
| H3 | **Verify production** on Clerk-only code: web/CLI/MCP-bearer/extension all work; the **deployed security suite** is green; and a **still-valid Auth0 token is now rejected** (401 — the Auth0 path is gone). | **[C]** + **[S]** for browser checks |
| H4 | **Observe through the rollback window defined at H entry** (above) — remain in H until *both* the pre-agreed minimum duration **and** the normal-use evidence (every iOS user + every known CLI client) have been satisfied; do **not** redefine the window after seeing early results. Rollback here = revert the H code deploy — the column/config/tenants are all still present, so it's clean. | **[S]** |

**Exit H:** Clerk-only code verified in production; rollback window elapsed with no issue.

---

## Phase I — Contract (staged: code deploy → fleet verification → schema migration)

Only after H's rollback window closes cleanly. **The column drop must not share a deploy with the code that stops reading it** — during a rolling deploy an old instance still mapping `users.auth0_id` would error against the dropped column. Stage it in three steps.

### I-code — deploy Clerk-only code that tolerates the old column/env still existing

| # | Step | Who |
|---|------|-----|
| Ia | Remove **all `users.auth0_id` reads/mapping** from the ORM/model and services (the column stays in the DB for now; the code simply stops referencing it). | **[C]** |
| Ib | **Cache**: drop the M1 transitional Auth0 cache key/fallback; remove `CachedUser.auth0_id`; **bump `CACHE_SCHEMA_VERSION`** (old entries are ignored → safe cache-miss to DB). | **[C]** |
| Ic | **Remove the Auth0 Settings surface** (`core/config.py`): the `auth0_domain`/`auth0_audience`/`auth0_client_id`/`auth0_custom_claim_namespace`/`auth0_jit_create_enabled` fields, the `auth0_issuer`/`auth0_jwks_url` helpers, and the **non-dev `AUTH0_CUSTOM_CLAIM_NAMESPACE` startup requirement** (`config.py:141`) — replaced by the Clerk-settings equivalent introduced in M1. This must land **here**, before J's env-var removal, or a retained validator crashes the api/cron services at startup. Env vars stay set for now (unreferenced = harmless). | **[C]** |
| Id | **Dev-mode synthetic user**: `auth0_id="dev\|local-development-user"` → an `external_auth_id` sentinel of the same shape/semantics; update `docs/architecture.md`. | **[C]** |
| Ie | **Tombstone retention**: add the `deleted_identities` sweep (entries older than **30 days**) to `tasks/cleanup.py` (daily) — safe **only now** (removing the Auth0 verification path ends the open-ended lifetime the Auth0-side tombstones guarded; 30 days ≫ the ~1-day Clerk token lifetime; see M8 step 2a). | **[C]** |
| If | **CLI source cleanup**: delete `TIDDLY_AUTH0_*` handling remnants. **Source-only — no user-facing CLI release is required** (users already upgraded at M6a); fold into the next routine `cli/v*` release if/when convenient. | **[C]** |
| Ig | **Deploy I-code**; run the full suite + deployed security tests. | **[C→S]** |

### I-verify — confirm the fleet is on I-code before touching the schema

| # | Step | Who |
|---|------|-----|
| Ih | Confirm **every** api **and** cron instance is running the I-code build (drain/replace any lingering old instance). The column drop is unsafe while any process still maps `auth0_id`. | **[C→S]** |

### I-migrate — drop the column

| # | Step | Who |
|---|------|-----|
| Ii | **Forward migration** (`make migration message="drop auth0_id and finalize clerk-only identity"`) — **contract amended 2026-07-31 (I-code review round) to cover both tables and all dev-sentinel states**: (1) preflight **both** `users` and `deleted_identities` for `external_auth_id IS NULL`; (2) dev-sentinel handling — when the *only* row carrying the sentinel is the legacy auth0-keyed one (`auth0_id='dev\|local-development-user'`, `external_auth_id IS NULL`), backfill its `external_auth_id`; when a **duplicate** exists (legacy row + a new external-keyed sentinel row), **fail the migration loudly** with instructions (reset the local DB or manually merge — never silently delete a row whose cascade would destroy a developer's local content); (3) any other `external_auth_id IS NULL` row → fail loudly (impossible in production per H1); (4) drop `ck_user_has_identity`, `users.auth0_id` + its index; drop `ck_deleted_identity_has_identity`, `deleted_identities.auth0_id` + its index; (5) **`SET NOT NULL` on `external_auth_id` in both tables**; (6) in the same PR, flip both ORM models to non-nullable `Mapped[str]`. Migration tests cover the three dev-DB states (clean / legacy-only / duplicated sentinel). **Never edit old migrations** — this is a new forward migration. Deploy; verify production again (full suite + deployed security tests). | **[C→S]** |

**Exit I:** I-code deployed and verified fleet-wide; column dropped; `external_auth_id` NOT NULL; cache / dev-sentinel / tombstone-sweep / CLI / Auth0 Settings all cleaned; production green.

---

## Phase J — Remove env vars, then delete the tenants (last)

| # | Step | Who |
|---|------|-----|
| J1 | **Remove obsolete env vars** — safe now because I-code (Ic) already removed the Settings fields and the non-dev namespace validator that read them, so nothing deployed references them: `AUTH0_*` on the Settings-loading services (api + the two cron services), **and `VITE_AUTH0_*` on the Railway *frontend* service** (build-time values; not a Settings-loading service, so easy to miss). Remove `@auth0/auth0-react` from the frontend. Remove `.env.example` Auth0 vars. | **[C→S]** |
| J2 | **Security tests**: update `backend/tests/security/` and `tests/security/deployed/` for the Clerk-only world (deployed tests use PATs — little change; update anything asserting Auth0-specific 401/403 text or claims). Operator runs `test_live_penetration.py` against production. | **[C]** + **[S]** |
| J3 | **Docs sweep** (AGENTS.md "Files to Keep in Sync"): `docs/architecture.md` (§5 auth rewrite, diagram nodes, Redis key schema, "known drift risks"), `README_DEPLOY.md` (Step 6 → Clerk, env tables, cron env vars), `README.md`, `AGENTS.md` (auth description), `.env.example`, the `llms.txt` family where auth is described (`llms-integration.txt` "Auth0-only 403 surfaces" → **already renamed to "session-only (403) surfaces" in the M5 docs pass, 2026-07-17 — verify, don't redo**), re-check `CONSENT_INSTRUCTIONS` in `core/auth.py`, and `docsRoutes.tsx`/`settingsRoutes.tsx` searchText if auth terms changed. Mark `future-identities.md` superseded (AD2). | **[C]** |
| J4 | **Grep gate**: no case-insensitive `auth0` in code/config outside `docs/` history and immutable historical migrations. **Ledger gate**: `grep '\[OPEN\]' docs/auth0-clerk-ledger.md` returns no marker pointing at a migration milestone. | **[C]** |
| J5 | **Ledger final pass**: total effort per milestone; the complete gained/lost/neutral table. | **[C→S]** |
| J6 | **Delete the Auth0 tenants (dev and prod) — LAST.** *(Precondition amended 2026-07-31: the archived-export requirement was resolved by the operator deleting the export — the H0 **database snapshot** is the surviving identity record; see the execution record.)* Preflight: confirm zero account deletions since 2026-07-31 (no new `deleted_identities` rows); if any exist, resolve them against the H0 snapshot and delete the matching Auth0 identities first. After deletion: remove the `README_DEPLOY.md` entry (expiry: J6) from `backend/tests/test_no_auth0_references.py`'s allowlist and delete README_DEPLOY's Auth0-side-cleanup subsection — the gate itself then flags them as stale if forgotten. This is the irreversible step; everything above is already verified Clerk-only in production. | **[S]** |

**Exit J (M6b done):** `make tests` clean; deployed security tests green against production; all sync-listed docs updated; grep + ledger gates pass; tenants deleted; export archived with a named retention owner.

---

## Execution record (updated as phases complete)

- **Gate G — EXECUTED 2026-07-31.** G1: cohort re-enumerated — two iOS users (maintainer + app developer) and one CLI user (maintainer); no other users/devices known. G2: directly confirmed — the Clerk iOS build (deployed 2026-07-17, Auth0 fully removed) verified live by a production save on 2026-07-31 (maintainer; also closed ledger Q9/Q11); the app developer confirmed migrated; the maintainer's CLI confirmed on the Clerk binary via authenticated `tiddly status`. G3 backstop agreed: production tenant's newest `last_login` 2026-07-16, tenant log stream empty over its retention window, zero `auth0_path_authentication` lines in api logs, zero Auth0 identities created post-cutoff.
- **H0 — EXECUTED 2026-07-31, export retention resolved by deletion.** Manual Railway Postgres backup taken (operator). Final Auth0 export: 11 users, full profiles via the Management API, taken and verified — then **deliberately deleted the same day by operator decision** ("it's not needed" at 11 stale profiles / 2 active users). Rationale: the H0 **database snapshot** already preserves the complete Clerk↔Auth0 identity mapping (the `users` table, frozen pre-column-drop) under Railway's managed backup retention, so a separate operator-held PII file duplicated that record while adding an unmanaged copy of every user's email. Deleting it is the stronger privacy posture. **This waives J6's "archived export stored safely" precondition** — the H0 DB snapshot is the surviving record; J6's gate is amended accordingly (see the residual record below).
- **H1 — EXECUTED 2026-07-31 (clean).** 13 users, 13 with `external_auth_id`, zero NULL, zero Auth0-only; window-signup reconciliation zero (0 Auth0 identities created after 2026-07-15) — closes M6a's waived-freeze residual.
- **H2/H3 — EXECUTED 2026-07-31.** Clerk-only code deployed (PR #162, merged and verified serving); deployed security suites green against production (48-test cross-user penetration + 10 auth/webhook — the same coverage recorded as "58 green" at M6a); web (fresh Clerk sign-in + note save), CLI (authenticated `tiddly status`), and PAT-path (the penetration suite is entirely PAT-based, covering the extension's auth class) all verified; an Auth0-issuer token probed live against a protected endpoint → 401. The claim-shape caveat: the probe token was not Auth0-signed, so it complements (not replaces) the mutation-proven dispatch test; the operator accepted skipping a real-Auth0-token mint as ceremony given the provider logs.
- **H4 — COMPRESSED by operator decision 2026-07-31** ("overkill for 2 primary users and a few beta users"): the evidence bar (one normal-use cycle per client class, zero Auth0-path traffic, zero Clerk errors) was met same-day; the elapsed-time component was waived. Phase I authorized by the operator the same day.
- **I-code accepted residuals (review round, 2026-07-31 — both accepted by the operator with these records):**
  - *Interval deletions drop the Auth0-side record.* From the I-code deploy until J6, an account deletion tombstones only the Clerk identity; the deleted user's Auth0 identity stays in the (soon-to-be-deleted) tenant with no per-user work-list entry. Guards: `AUTH0_JIT_CREATE_ENABLED=false` persists on Railway until J1 and is the fail-closed backstop against any Auth0-path resurrection under a **full** revert (caveat, recorded deliberately: a partial cherry-pick restoring only the verification arm without the Settings field would not inherit it — an unusual action, not a routine rollback); the H0 DB snapshot preserves the Clerk↔Auth0 mapping if reconciliation is ever needed. **J6 preflight (added):** confirm zero `user.deleted` deliveries / new tombstone rows since 2026-07-31; if any exist, resolve them against the H0 snapshot's `users` table and delete the matching Auth0 identities before tenant deletion.
  - *Mixed-version cache window during the I-code deploy.* Cache keys move v6→v7; during the deploy overlap the draining instance can serve a v6 entry that a deletion processed by the new instance cannot invalidate. Bound: the lesser of the old container's drain lifetime and the 5-minute TTL; deterministic-but-silent during every mixed-version overlap (distinct from the M8 partial-Redis-failure residual, which logs). Accepted at single-instance Railway topology, with an observable gate folded into I-verify (Ih): confirm the old container terminated **and** confirm no `user.deleted` landed during the rollout (query `deleted_identities` for rows created in the deploy window) before declaring I-verify complete.
- **I-code (Ia–Ig) — EXECUTED 2026-07-31.** PR #163 merged and deployed; `make backend-verify` green pre-merge (3,470); the new Alembic-head schema-compatibility test proves the Clerk-only write surface against the pre-migration production schema. Post-deploy: full deployed security suites green against production (48 cross-user penetration + 10 auth/webhook = the 58 recorded at M6a).
- **Ih (I-verify) — EXECUTED 2026-07-31.** Every service (api, cleanup, ai-usage-flush, both MCP servers, frontend) on the I-code commit (`9a7f3a3`), api's old container status REMOVED with a single RUNNING replacement; zero `deleted_identities` rows created during the rollout window (the cache-residual gate above, satisfied); ai-usage-flush completed a scheduled run on the new build.
- **Policy re-consent rides the Ii deploy (final review round, 2026-07-31):** the privacy policy and terms changed their identity-processor disclosure (Auth0 → Clerk), so `PRIVACY_POLICY_VERSION` and `TERMS_OF_SERVICE_VERSION` both advanced to `2026-07-31` — every user re-consents once. **Post-deploy checklist addition**: the 451 consent gate fires on ALL authenticated API surfaces until re-consent, including the two PAT-only security-test accounts — refresh their consent via the documented `curl -X POST /consent/me` path BEFORE running the deployed security suites, then verify web re-consent (dialog), one CLI/MCP request receiving actionable 451 instructions and succeeding after consent, and the extension.
- **Ii — migration authored 2026-07-31** (`867f3d604c7c`, per the amended contract: both tables, both CHECKs/indexes, `SET NOT NULL` ×2, backfill-or-fail dev-sentinel handling, fail-loud preflights; ORM models flipped to non-nullable in the same change). State-tested against real `alembic upgrade` runs: clean DB migrates; legacy-only sentinel backfills with content preserved; duplicated sentinel aborts loudly deleting nothing; stray NULL aborts. Ships in the close-out PR; deploys via the api service's pre-deploy `alembic upgrade head`.

---

## Rollback boundaries (where the door is still open)

- **Through Phase H and I-code (before I-migrate):** revertible — revert the code deploy; `users.auth0_id`, the Auth0 env vars, and both tenants all still exist, so dual-accept can be restored (re-add the verification path + Settings fields from git history).
- **After I-migrate (column dropped):** the schema door has closed; re-introducing Auth0 is a rebuild, not a revert. Treat this as the practical point of no return for the Auth0 *code path*. The **tenants still exist**, so identities/data are still recoverable from Auth0 until J6.
- **After J6 (tenants deleted):** irreversible. This is why J6 is last and gated on the archived export.
