# Deployment Guide

Deploy Tiddly services to Railway using Docker.

## Architecture

| Service | Description | Build |
|---------|-------------|-------|
| **api** | FastAPI backend | `Dockerfile.api` |
| **content-mcp** | Content MCP server (bookmarks/notes) | Railpack |
| **prompts-mcp** | Prompt MCP server (prompts capability) | Railpack |
| **frontend** | React SPA | Railpack |
| **ai-usage-flush** | Hourly cron that flushes Redis AI cost buckets into `ai_usage` | `Dockerfile.api` |
| **cleanup** | Daily cron: tier-based history retention + soft-delete expiry + orphan-history sweep | `Dockerfile.api` |
| **orphan-relationships** | Daily cron: detects (and optionally deletes) rows in `content_relationships` whose source/target entity no longer exists. **Deferred — documented for future deploy but not running in production** ([KAN-67](https://tiddly.atlassian.net/browse/KAN-67); see `docs/architecture.md` §9) | `Dockerfile.api` |
| **Postgres** | PostgreSQL database | (managed by Railway) |
| **Redis** | Rate limiting and auth cache | (managed by Railway) |

> **Cross-stack tier data:** every `Dockerfile.api`-built service (api + the three crons) reads subscription tier limits from `frontend/src/content/data/tiers.json` at startup (`core/tier_limits.py`) and **fails fast on boot if it's missing**. `Dockerfile.api` `COPY`s the file into the image at the same path. Its watch paths include `frontend/src/content/data/tiers.json` so editing a tier limit redeploys the backend (otherwise enforcement would lag the published Pricing page until the next backend deploy).

---

## Prerequisites

1. [Railway account](https://railway.app)
2. [Railway CLI](https://docs.railway.com/guides/cli) installed:
   ```bash
   npm install -g @railway/cli
   railway login
   ```
3. Clerk account with the Tiddly application (see Step 6)

---

## Initial Setup

### Step 1: Create Railway Project

```bash
railway init
```

Or via dashboard: Click **+ New Project** → **Empty Project**

### Step 2: Add PostgreSQL

In the Railway dashboard:
1. Press `Cmd+K` (Mac) or `Ctrl+K` (Windows)
2. Type "Postgres" and select **Add PostgreSQL**

Railway automatically creates these variables on the Postgres service:
- `DATABASE_URL`
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`

### Step 2b: Add Redis

In the Railway dashboard:
1. Click `Create`
2. Type "Redis" and select **Add Redis**

Railway automatically creates these variables on the Redis service:
- `REDIS_URL`
- `REDISHOST`, `REDISPORT`, `REDISUSER`, `REDISPASSWORD`

Redis is used for:
- **Rate limiting**: Tiered limits by auth type (PAT vs IdP session) and operation type
- **Auth caching**: 5-minute TTL cache for user lookups to reduce database load
- **Fail-open mode**: If Redis is unavailable, requests are allowed (degraded mode)

### Step 3: Create Services

Create the services (6 deployed today; `orphan-relationships` is deferred — see the table above), each connected to your GitHub repo:

1. Click **+ Create** → **GitHub Repo** → Select `tiddly`
2. Repeat for each service (all pointing to the same repo)

All are created the same way — Railway does NOT have a distinct "Cron Job" service type. The cron services (`ai-usage-flush`, `cleanup`, and — when it's eventually deployed — `orphan-relationships`) become crons by setting a **Cron Schedule** on each in Step 4; everything else is a regular long-running service. Production currently runs **six** services (`orphan-relationships` is deferred, per the table above).

### Step 4: Configure Each Service

Click on each service → **Settings** tab → Configure as follows:

#### API Service

**Settings → Source:**
- Rename service to `api` (click the name at top)
- Enable **Wait for CI** (deploys only after GitHub Actions pass)

**Settings → Build:**
- Builder: **Dockerfile**
- Dockerfile Path: `/Dockerfile.api`
- Watch Paths: `backend/**`, `pyproject.toml`, `Dockerfile.api`, `frontend/src/content/data/tiers.json`

**Settings → Deploy:**
- No Custom Start Command needed (the Dockerfile handles this)
- Pre-Deploy Command: `uv run alembic upgrade head` (runs database migrations automatically before each deployment)

**Settings → Networking:**
- Click **Generate Domain** (public, for external access)
- Click **+ Private Domain** → set to `api.railway.internal` (for internal service-to-service communication)

#### Content MCP Service

**Settings → Source:**
- Rename service to `content-mcp`
- Enable **Wait for CI**

**Settings → Build:**
- Build Command: `uv sync --no-dev`
- Watch Paths: `backend/**`, `pyproject.toml`

**Settings → Deploy:**
- Start Command: `cd backend/src && uv run python -m mcp_server`

**Settings → Networking:**
- Click **Generate Domain**

#### Prompt MCP Service

**Settings → Source:**
- Rename service to `prompts-mcp` (the deployed service name — commands below and any `${{prompts-mcp....}}` references depend on it)
- Enable **Wait for CI**

**Settings → Build:**
- Build Command: `uv sync --no-dev`
- Watch Paths: `backend/**`, `pyproject.toml`

**Settings → Deploy:**
- Start Command: `cd backend/src && uv run python -m prompt_mcp_server`

**Settings → Networking:**
- Click **Generate Domain**

#### Frontend Service

**Settings → Source:**
- Rename service to `frontend`
- Root Directory: `/frontend`
- Enable **Wait for CI**

**Settings → Networking:**
- Click **Generate Domain**

#### AI Usage Flush Service (Cron)

Hourly job that flushes Redis AI-cost buckets into the `ai_usage` Postgres table. Runs as a regular Railway service with a cron schedule attached — Railway does not have a separate "Cron Job" service type. Runs independently of the API so its failure mode is isolated.

**Settings → Source:**
- Rename service to `ai-usage-flush`
- Enable **Wait for CI**

**Settings → Build:**
- Builder: **Dockerfile**
- Dockerfile Path: `/Dockerfile.api`
- Watch Paths: `backend/**`, `pyproject.toml`, `Dockerfile.api`, `frontend/src/content/data/tiers.json`

**Settings → Deploy:**
- **Cron Schedule:** `30 * * * *` (every hour at :30, UTC). Railway's minimum interval is 5 minutes.
- **Custom Start Command:** `uv run python -m tasks.ai_usage_flush`
  - For Dockerfile deploys this overrides the image's `CMD` in **exec form** (no shell). The command has no shell constructs and `PYTHONPATH=/app/backend/src` is already baked into `Dockerfile.api`, so no shell wrapping or `cd` is needed.
- **Pre-Deploy Command:** leave empty (migrations are owned by the api service).

**Settings → Networking:**
- No public domain — the cron writes to Postgres/Redis over Railway's private network only.

**Cron behavior on Railway (worth knowing before first run — applies to all three cron services):**
- Schedules are UTC.
- Execution time can drift by a few minutes — Railway does not guarantee minute precision.
- If a prior run is still in flight when the next tick fires, Railway **skips** the new execution.
- The cron process must exit when the task completes. All three scripts (`ai_usage_flush.py`, `cleanup.py`, `orphan_relationships.py`) use `asyncio.run(...)` and exit cleanly.
- The Cron Runs tab has a **Run now** button to trigger an ad-hoc execution of the current deployment. Useful for verifying the cron works after a config change without waiting for the next scheduled tick. Alternatively, to force the normal scheduled path, temporarily change the schedule to a near-future expression (e.g. `*/5 * * * *`), observe a run, then revert.
- If a push to `main` doesn't trigger a redeploy (occasionally observed for cron services), force a fresh build against the current `main` HEAD: `Cmd+K` on the service in the Railway dashboard → **Deploy latest commit**. Confirm the new code is live via the version marker in the cron's start-up log line (see next bullet).
- Each cron logs a version marker on start — e.g., `cleanup.py` logs `Starting cleanup task (version=...)` using `CLEANUP_TASK_VERSION` (UTC timestamp, `YYYY-MM-DDTHH:MMZ`). Update the constant to the current UTC time when shipping changes; the log line then confirms at a glance whether a given run is on the new code.
- The `ai_usage_flush` upsert uses SET (not INCREMENT), and `cleanup` / `orphan-relationships` are idempotent by construction — so re-runs of any service are safe.

#### Cleanup Service (Cron)

Daily job that enforces tier-based history retention (`content_history`), permanently deletes soft-deleted items older than 30 days, and sweeps orphan `content_history` rows whose entity was hard-deleted. DB-only — does not need Redis.

**Settings → Source:**
- Rename service to `cleanup`
- Enable **Wait for CI**

**Settings → Build:**
- Builder: **Dockerfile**
- Dockerfile Path: `/Dockerfile.api`
- Watch Paths: `backend/**`, `pyproject.toml`, `Dockerfile.api`, `frontend/src/content/data/tiers.json`

**Settings → Deploy:**
- **Cron Schedule:** `0 3 * * *` (daily at 03:00 UTC)
- **Custom Start Command:** `uv run python -m tasks.cleanup`
- **Pre-Deploy Command:** leave empty.

**Settings → Networking:**
- No public domain.

#### Orphan Relationships Service (Cron) — deferred, not currently deployed

**This service is intentionally not running in production** at current scale ([KAN-67](https://tiddly.atlassian.net/browse/KAN-67)); the section is kept as the setup reference for when it deploys. Daily job that finds rows in `content_relationships` whose source or target entity no longer exists, and (when `--delete` is passed) deletes them. Independent of the `cleanup` service — separate failure mode. DB-only.

**Settings → Source:**
- Rename service to `orphan-relationships`
- Enable **Wait for CI**

**Settings → Build:**
- Builder: **Dockerfile**
- Dockerfile Path: `/Dockerfile.api`
- Watch Paths: `backend/**`, `pyproject.toml`, `Dockerfile.api`, `frontend/src/content/data/tiers.json`

**Settings → Deploy:**
- **Cron Schedule:** `0 4 * * *` (daily at 04:00 UTC — offset by an hour from `cleanup` so they don't pile on the DB simultaneously)
- **Custom Start Command:** start in **report-only mode first**, then switch to delete mode once verified.
  - **Initial (report-only):** `uv run python -m tasks.orphan_relationships`
  - **After verifying zero-or-small orphan counts:** `uv run python -m tasks.orphan_relationships --delete`
- **Pre-Deploy Command:** leave empty.

**Settings → Networking:**
- No public domain.

**Why report-only first:** `content_relationships` is write-light and orphans should be near-zero on a healthy system. Running in report mode for one cycle confirms the detector isn't finding false positives (e.g. a live entity it can't see due to a model misalignment) before you authorize deletes.

### Step 5: Configure Environment Variables

Click on each service → **Variables** tab.

#### API Service Variables

Click **New Variable** or use **RAW Editor** to add:

```
DATABASE_URL=postgresql+asyncpg://<manually-set-see-below>
REDIS_URL=${{Redis.REDIS_URL}}
CORS_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
VITE_API_URL=https://${{api.RAILWAY_PUBLIC_DOMAIN}}
VITE_FRONTEND_URL=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}
CLERK_FRONTEND_API=clerk.tiddly.me
CLERK_AUTHORIZED_PARTIES=https://tiddly.me
API_WORKERS=4
```

**Clerk (the sole IdP):** `CLERK_FRONTEND_API` (the production instance's Frontend API domain) and `CLERK_AUTHORIZED_PARTIES` (comma-separated web origins accepted as the `azp` claim) are **required** — Settings validation refuses to start without them in non-dev mode. Clerk has been the **primary production IdP since the M6a cutover (2026-07-15)** and the **only accepted token issuer since the M6b expand deploy (2026-07-31)**. The JIT-create flag is actively set (non-default) on the api service — kept post-migration as a sign-up kill switch:

```
CLERK_JIT_CREATE_ENABLED=true    # flipped at the 2026-07-15 cutover (code default: false)
```


**Account-deletion webhook:** `CLERK_WEBHOOK_SIGNING_SECRET` (the `whsec_...` secret of the production instance's webhook endpoint — see Step 6f). API service only. Unset, `POST /webhooks/clerk` fails closed with 503; Svix retries on a finite ~28-hour schedule and then marks deliveries Failed (manual replay only — see the Step 6f runbook).

**Note:** `VITE_API_URL` and `VITE_FRONTEND_URL` are used by the backend to generate helpful error messages (e.g., consent enforcement instructions).

**Important: DATABASE_URL must be set manually.** Railway's Postgres provides `postgresql://` but this app requires `postgresql+asyncpg://` for async SQLAlchemy. Do NOT use `${{Postgres.DATABASE_URL}}`.

**Note:** `REDIS_URL` can use the Railway variable reference `${{Redis.REDIS_URL}}`. Redis fails open, so the app works even if Redis is temporarily unavailable.

To set DATABASE_URL:
1. Click the **Postgres** service → **Variables** tab
2. Copy the `DATABASE_URL` value (e.g., `postgresql://user:pass@host:5432/railway`)
3. Go back to the **api** service → **Variables** tab
4. Add `DATABASE_URL` and paste the copied value
5. Change `postgresql://` to `postgresql+asyncpg://` at the start of the URL

**Optional tuning variables** (defaults are fine for most cases, see [docs/connection-pool-tuning.md](docs/connection-pool-tuning.md)):

| Variable | Default | Description |
|----------|---------|-------------|
| `API_WORKERS` | `1` | Uvicorn worker processes (set to `4` for Railway's 8 vCPU) |
| `DB_POOL_SIZE` | `10` | Persistent DB connections per worker |
| `DB_MAX_OVERFLOW` | `10` | Temporary DB connections per worker |
| `DB_POOL_RECYCLE` | `3600` | Recycle connections older than N seconds |
| `REDIS_POOL_SIZE` | `5` | Redis connections per worker |

**AI / LLM variables:**

Only `OPENAI_API_KEY` is required for the initial deploy. The only AI use case wired up today (suggestions) defaults to `openai/gpt-5.4-nano`, and platform users are locked to the use-case default in code — no other platform key is reachable on the platform path. BYOK users supply their own keys via the `X-LLM-Api-Key` header and do not depend on these vars.

```
OPENAI_API_KEY=<your OpenAI key>
```

Add the following **when additional AI use cases ship** (TRANSFORM / AUTO_COMPLETE default to Gemini; CHAT defaults to OpenAI):

```
GEMINI_API_KEY=<your Google AI Studio key>
ANTHROPIC_API_KEY=<your Anthropic key>
```

Optional per-use-case model overrides (change only if you want to deviate from defaults — and add the matching provider key if the override points to a different provider):

```
LLM_MODEL_SUGGESTIONS=openai/gpt-5.4-nano
LLM_MODEL_TRANSFORM=gemini/gemini-flash-lite-latest
LLM_MODEL_AUTO_COMPLETE=gemini/gemini-flash-lite-latest
LLM_MODEL_CHAT=openai/gpt-5.4-mini
```

**Database migrations:** `ai_usage` and `ai_usage_analytics` (Postgres view used by the analytics role, see Step 8) are applied automatically by the pre-deploy `alembic upgrade head` command configured on this service — no manual migration step is needed.

#### AI Usage Flush Service Variables

```
DATABASE_URL=postgresql+asyncpg://<same value as api service>
REDIS_URL=${{Redis.REDIS_URL}}
CLERK_FRONTEND_API=<same value as api service>
CLERK_AUTHORIZED_PARTIES=<same value as api service>
```

Follow the same `postgresql+asyncpg://` rule as the API service (manually copy the Postgres URL and replace the `postgresql://` prefix — do NOT use `${{Postgres.DATABASE_URL}}` directly).

**Why `CLERK_FRONTEND_API` and `CLERK_AUTHORIZED_PARTIES` are required even for a cron:** the cron imports `db.session`, which instantiates `Settings()` at module load. The Settings validator (`core/config.py`) hard-requires both in non-dev mode as a safety check against silent identity-provider misconfiguration on the API. Cron tasks don't touch auth, but they share the same Settings class. Without these vars, the container crashes at import.

#### Cleanup Service Variables

DB-only; no Redis needed.

```
DATABASE_URL=postgresql+asyncpg://<same value as api service>
CLERK_FRONTEND_API=<same value as api service>
CLERK_AUTHORIZED_PARTIES=<same value as api service>
```

Same `postgresql+asyncpg://` rule as above. `CLERK_FRONTEND_API` and `CLERK_AUTHORIZED_PARTIES` are required for the same reason as above — Settings validation.

#### Orphan Relationships Service Variables

DB-only; no Redis needed.

```
DATABASE_URL=postgresql+asyncpg://<same value as api service>
CLERK_FRONTEND_API=<same value as api service>
CLERK_AUTHORIZED_PARTIES=<same value as api service>
```

Same `postgresql+asyncpg://` rule as above. `CLERK_FRONTEND_API` and `CLERK_AUTHORIZED_PARTIES` are required for the same reason as above — Settings validation.

#### Content MCP Service Variables

```
VITE_API_URL=http://api.railway.internal:8080
CONTENT_MCP_RESOURCE_URL=https://content-mcp.tiddly.me/mcp
CLERK_FRONTEND_API=<clerk frontend API host, e.g. clerk.tiddly.me — no scheme>
MCP_ALLOWED_ORIGINS=   # leave UNSET until a real connector origin is verified — unset ≡ empty (both fail closed), and the Railway CLI rejects empty values
```

**Note:** Railway automatically provides the `PORT` variable - do not set it manually.

#### Prompt MCP Service Variables

```
VITE_API_URL=http://api.railway.internal:8080
PROMPT_MCP_RESOURCE_URL=https://prompts-mcp.tiddly.me/mcp
CLERK_FRONTEND_API=<clerk frontend API host, e.g. clerk.tiddly.me — no scheme>
MCP_ALLOWED_ORIGINS=   # leave UNSET until a real connector origin is verified — unset ≡ empty (both fail closed), and the Railway CLI rejects empty values
```

**Note:** Railway automatically provides the `PORT` variable - do not set it manually.

**Use the literal custom domain, not a `${{...RAILWAY_PUBLIC_DOMAIN}}` reference.** The resource URL doubles as the transport's Host allowlist (DNS-rebinding protection), so it must be the domain clients actually connect to. Both MCP services use custom domains; `RAILWAY_PUBLIC_DOMAIN` resolves to the Railway-generated domain instead, which would advertise the wrong `resource` **and** reject (421) every request arriving at the real domain.

**MCP OAuth variables (M5) — stage these BEFORE merging the OAuth code (fail-fast, deploy-on-merge).** Each MCP server validates its OAuth discovery config at startup: a missing or malformed `*_MCP_RESOURCE_URL` (must be the server's own full `/mcp` endpoint) or `CLERK_FRONTEND_API` (a bare hostname) now **crashes the service on boot** rather than silently serving broken discovery. Because merging deploys the MCP services, set and verify both variables on **both** MCP services first, then merge — otherwise the auto-deploy takes the whole service down (not just OAuth), including existing bearer/PAT MCP users. `MCP_ALLOWED_ORIGINS` (browser-`Origin` allowlist for the `/mcp` transport) stays empty until the connector verification ladder confirms real connector origins; add them there, independently verified as provider-owned — never by copying rejected-Origin log lines.

**Known operational issue — ChatGPT connector sign-ins fail until patched (OpenAI bug).** ChatGPT's dynamic client registration omits the `openid` scope its own sign-in request later demands, so every new ChatGPT connector registration bounces at the Clerk authorize step until an operator adds `openid` to that registration's scopes (one `clerk api /oauth_applications/{id}` PATCH — exact command, diagnosis evidence, and the OpenAI acknowledgment link in `docs/implementation_plans/2026-07-16-mcp-connector-verification-notes.md`). Policy: patch on request, with operator approval — this is a Clerk-side data fix, never a server code change. Claude/Codex/Inspector registrations are unaffected.

**Why `http` and not `https`?** The MCP servers communicate with the API over Railway's private network, which never leaves Railway's infrastructure. TLS is unnecessary for internal traffic and skipping it reduces latency. The frontend must still use the public `https` URL since it runs in the user's browser.

#### Frontend Service Variables

```
VITE_API_URL=https://api.tiddly.me
VITE_MCP_URL=https://content-mcp.tiddly.me
VITE_PROMPT_MCP_URL=https://prompts-mcp.tiddly.me
VITE_CLERK_PUBLISHABLE_KEY=<pk_live_... from the production Clerk instance>
```

Use the **literal custom domains** (matching the live services), not `${{...RAILWAY_PUBLIC_DOMAIN}}` references — those resolve to the Railway-generated domains, and the values here are user-facing (the app displays the MCP URLs for connector setup).

**Note:** Railway may warn about egress fees for `VITE_API_URL` and `VITE_MCP_URL` referencing public endpoints. You can ignore this - the frontend is a static SPA, so all API calls happen from the user's browser, not between Railway services.

### Step 6: Configure Clerk

Clerk provides authentication for the web app (embedded sign-in components, no hosted redirect page) and token verification material for the backend. One Clerk **application** carries two paired **instances**: development (`pk_test_`/`sk_test_`, works on localhost with no DNS) and production (`pk_live_`/`sk_live_`, requires DNS on your domain). Users and secrets never transfer between instances; configuration is promoted dev → prod with `clerk deploy`.

This section is deliberately specific about WHAT must exist in Clerk and gives only general dashboard direction — dashboard click-paths rot; settings do not. Nearly everything below is scriptable through the Clerk CLI (`clerk auth login` once, then `clerk apps create`, `clerk config pull/patch/put`, `clerk deploy`, `clerk env pull`); the committed `clerk/config.dev.json` is the reviewable source of truth for instance configuration (see `clerk/README.md`).

> **Migration history (see `docs/implementation_plans/2026-07-02-clerk-migration.md`):** Clerk is the only identity provider. The app ran on Auth0 until the 2026-07-15 cutover and dual-accepted both issuers through a migration window; the M6b decommission (2026-07-31) removed the Auth0 verification path, all code references, the database columns, the environment variables, and finally the Auth0 tenants themselves. Nothing in this guide depends on Auth0 anymore.

#### 6a. Application and instances

What must exist: a Clerk application (ours: "Tiddly") with its development instance, and a production instance bound to the apex domain (`tiddly.me`).

1. `clerk apps create "Tiddly"` creates the application + development instance.
2. `clerk deploy` (interactive, human terminal) creates the production instance, registers the domain, clones the dev configuration to production, and prints the DNS records and OAuth to-dos. `clerk deploy status` (read-only) reports pending records and validation state at any time.

#### 6b. DNS records (production instance only)

Five CNAME records on the domain, values printed by `clerk deploy` (the mail values are instance-specific):

| Host | Purpose |
|---|---|
| `clerk.<domain>` | Frontend API — serving Clerk from your own subdomain keeps the session cookie first-party (load-bearing for the ~60s token refresh as browsers phase out third-party cookies) |
| `accounts.<domain>` | Hosted Account Portal |
| `clkmail.<domain>` | Transactional email (sign-in codes, resets) from your domain |
| `clk._domainkey.<domain>`, `clk2._domainkey.<domain>` | DKIM for the above |

Records must be **DNS-only (not proxied)** or Clerk's validation fails. Propagation + SSL issuance can take up to 48h (typically minutes). Monitor via `clerk deploy status` or Dashboard → Domains.

#### 6c. Instance configuration (both instances — promoted from the committed dev config)

What must exist (all present in `clerk/config.dev.json`; apply to prod via `clerk deploy` or `clerk config put --instance prod --file clerk/config.dev.json`):

- **Auth strategies**: email/password enabled; `email_code` enabled as a sign-in strategy (this is what gives passwordless-imported users their first sign-in path); Google social connection enabled.
- **Session token custom claims** (`session.claims`): `email` = `{{user.primary_email_address}}`, `email_verified` = `{{user.email_verified}}` — the backend reads these plain (non-namespaced) claims.
- **Session clock skew** (`session.allowed_clock_skew`): 5s (default) — the backend independently applies `leeway=5` in its own verification; the two are set to match.
- **Sign-up mode** (`auth_access_control.sign_up_mode`): `public` on production since the M6a cutover reopened sign-ups (2026-07-15); it was `restricted` from instance activation until the cutover reconciled the user import. (Dev stays `public`.)
- **MFA and passkeys**: off (deferred with the Pro-plan decision; see the migration plan's adoption register).

#### 6d. Google social connection (production credentials)

Dev instances use Clerk's shared Google credentials; production requires your own:

1. Google Cloud Console → your existing OAuth **Web application** client (the same one may serve multiple IdPs) → add Clerk's **authorized redirect URI** for the production instance — copy the exact value from Dashboard → SSO connections → Google (it is served from your Frontend API domain, e.g. `https://clerk.<domain>/v1/oauth_callback`; always paste what Clerk displays).
2. Provide the Client ID + Client Secret to the production instance's Google connection (via re-running `clerk deploy`, or the dashboard's Google connection settings). Use **custom credentials**, not Clerk's development-shared ones.

#### 6e. Environment variables recap

- Frontend service: `VITE_CLERK_PUBLISHABLE_KEY` (`pk_live_...`; `clerk env pull --instance prod` fetches it). An empty key makes the frontend fall back to dev mode (auth bypassed).
- API + cron services: `CLERK_FRONTEND_API`, `CLERK_AUTHORIZED_PARTIES`; the api service also sets both JIT-create flags explicitly post-M6a (crons may omit them — Settings defaults apply) — see the API Service Variables section above.
- The Clerk **secret key** is not deployed anywhere: the backend verifies tokens against the public JWKS (networkless); the secret key is used only by the one-off M2 import script, run from an operator machine.
- API service additionally: `CLERK_WEBHOOK_SIGNING_SECRET` (see 6f). Not required by Settings validation (crons don't need it); without it the webhook endpoint fails closed with 503.

#### 6f. Webhook endpoint — account deletion (both instances)

The backend exposes `POST /webhooks/clerk` (Svix-verified), subscribed to `user.deleted`: a Clerk-side account deletion cascade-deletes the user's Tiddly data and tombstones the identity against JIT resurrection. What must exist, per instance (webhook endpoints and their secrets do not transfer between instances):

1. Dashboard → Webhooks → Add endpoint, URL `https://<api-host>/webhooks/clerk`, subscribed to the `user.deleted` event only. (Dev instance: the endpoint URL is a tunnel to locally-running code — cloudflared/ngrok — recreated per test session, not permanent.)
2. Copy that endpoint's **signing secret** (`whsec_...`) into the API service's `CLERK_WEBHOOK_SIGNING_SECRET`.
3. Only after 1–2 are verified (Dashboard → Webhooks → endpoint → send a test `user.deleted` event → 200) **and the delivery-failure detection below has a named owner**, enable user-initiated deletion: `user_settings.actions.delete_self` (Dashboard → User & authentication → User model — dashboard-only, not in the config CLI schema). This one switch governs the deletion section in both the embedded `<UserProfile />` and the hosted Account Portal. It stays OFF until the webhook is live — a deletion with no webhook handler orphans the user's data.

Ordering note: the production webhook endpoint + secret must be configured **before** users exist in the production instance (an M6a pre-flip requirement — the hosted Account Portal is a Clerk-rendered surface the app cannot gate).

**Delivery-failure detection and replay (runbook).** Svix delivery is finite: 8 attempts over ~28 hours (immediate, 5s, 5m, 30m, 2h, 5h, 10h, 10h; a 2xx must arrive within 15s), then the message is marked **Failed** — after which nothing deletes the user's Tiddly data until an operator acts. Because deletion is self-service, an exhausted `user.deleted` delivery is a **privacy-affecting incident the operator won't otherwise know about** ("check when a deletion is expected" doesn't work — nobody expects a self-service deletion). Requirements:

- **Detection — named owner and cadence**: the operator (Shane) reviews Dashboard → Webhooks → endpoint attempt/failure list **weekly, and after any API outage longer than an hour**. (If Clerk exposes endpoint-failure email notifications, enable them and the cadence becomes a backstop. Svix also fires a `message.attempt.exhausted` operational webhook on exhaustion — the ready-made trigger if automated alerting is built later; deliberately not built at current scale.)
- **Replay**: Dashboard → Webhooks → endpoint → the failed message → Resend (or "recover failed messages since date"). The handler is idempotent — replaying an already-processed deletion is always safe.
- **Verify the postcondition**: the user's row is gone (`SELECT 1 FROM users WHERE external_auth_id = '<clerk user id>'` → no row) and a tombstone exists in `deleted_identities`.

### Step 7: Deploy

Push your changes to `main` branch. With **Wait for CI** enabled, Railway will:
1. Wait for GitHub Actions tests to pass
2. Then automatically deploy all services

**Note:** If you click **Deploy** in the dashboard before pushing, you'll see "Deployment waiting" until CI passes. Push to `main` to trigger the GitHub Actions workflow.

### Step 8: Post-Deploy AI Configuration

One-time setup required the first time you enable AI features. Only the OpenAI cap (8a) is a hard requirement for the initial deploy.

#### 8a. Provider spend caps (required)

Configure a monthly spend cap on every provider whose platform key is set on the API service. Provider-enforced caps suspend service when reached, so this is the primary safeguard against runaway cost — there is no application-level circuit breaker.

- **OpenAI** (required today — platform default for suggestions): [OpenAI billing dashboard → limits](https://platform.openai.com/account/limits). Set a monthly budget before enabling Pro-tier AI access.
- **Google AI Studio** (add when Gemini-backed use cases ship): set a project-level monthly spend cap (e.g. $50/month) in the Google AI Studio console.
- **Anthropic** (add when Anthropic-backed use cases ship): set a monthly spend limit in the Anthropic console.

Do not skip this — an unbounded platform key is the single largest cost-exposure risk of the AI feature set.

#### 8b. Analytics reader role (optional, recommended)

Create a separate read-only Postgres login scoped to the `ai_usage_analytics` view. The view replaces `user_id` with a pseudonymized `user_hash` (SHA-256) and exposes only cost/usage fields — no content tables, no auth tables, not even the base `ai_usage` table. Run this **manually** via Railway's database shell. Do NOT put credentials in migrations or source control.

```sql
-- Create the role with a strong, randomly generated password
CREATE ROLE analytics_reader LOGIN PASSWORD '<generated-password>';

-- Allow connection to the database and visibility into the public schema
GRANT CONNECT ON DATABASE railway TO analytics_reader;
GRANT USAGE ON SCHEMA public TO analytics_reader;

-- Grant SELECT on the analytics view ONLY — never the base `ai_usage` table
GRANT SELECT ON ai_usage_analytics TO analytics_reader;
```

Connection string for analytics tools / local CLI (Railway Postgres requires SSL):

```bash
psql "postgresql://analytics_reader:<password>@<railway-host>:<port>/railway?sslmode=require"
```

Use a separate role per consumer (one for each analytics tool, one for CLI) so credentials can be revoked independently. To grant access to a future analytics view, create the view with only the columns needed and `GRANT SELECT` on it to this role — do not widen access to base tables.

The `ai_usage_analytics` view and the `pgcrypto` extension it depends on are created by the `38f5a24e651f` migration and ship with the deploy. No schema work is needed before running the role/GRANT SQL above.

---

## Verify Deployment

1. **API:** Visit `https://<api-domain>/docs` - should show FastAPI docs
2. **Frontend:** Visit `https://<frontend-domain>` - should show login page
3. **Content MCP:** Visit `https://<content-mcp-domain>/mcp` - should respond to MCP requests
4. **Prompt MCP:** Visit `https://<prompts-mcp-domain>/mcp` - should respond to MCP requests
5. **AI Usage Flush cron:** Railway dashboard → `ai-usage-flush` service → **Deployments** tab. Verify at least one run has occurred at `:30` past the hour. One of three log outputs is expected:
   - `ai_usage_flush: no keys found` — Redis has no `ai_stats:*` keys at all (no AI traffic yet)
   - `ai_usage_flush: no completed hourly buckets to flush` — keys exist but only for the current hour (the flush intentionally excludes in-flight hours)
   - `ai_usage_flush: complete` — buckets were flushed, logged with `keys_processed` and `total_cost_flushed`
6. **Cleanup cron:** Railway dashboard → `cleanup` service → **Deployments** tab. After the first `0 3 * * *` UTC run, logs start with `Starting cleanup task` and end with `Cleanup complete: {...}` containing `soft_deleted_expired`, `expired_deleted`, `orphaned_deleted`. Any exceptions are surfaced via Railway's deployment failure indicator.
7. **Orphan Relationships cron** *(skip — deferred, not deployed; applies only once KAN-67 deploys it)*: Railway dashboard → `orphan-relationships` service → **Deployments** tab. After the first `0 4 * * *` UTC run, logs start with `Starting orphan relationship cleanup (delete=...)` and end with `Orphan relationship cleanup complete: {...}` containing `orphaned_source`, `orphaned_target`, `total_deleted`. Expect all zeros on a healthy system. **Before switching to `--delete`:** confirm `orphaned_source + orphaned_target = 0` for at least one scheduled run in report-only mode.
8. **AI endpoints** (requires a session token — PATs are blocked on these surfaces):
   ```bash
   curl -H "Authorization: Bearer <token>" https://<api>/ai/health
   # → {"available": true, "byok": false,
   #    "remaining_per_minute": ..., "limit_per_minute": ...,
   #    "remaining_per_day": ..., "limit_per_day": ...,
   #    "resets_at": null}   // ISO 8601 UTC; null until first AI call in the window

   curl -H "Authorization: Bearer <token>" https://<api>/ai/models
   # → {"models": [...7 models...], "defaults": {...}}
   ```
9. **Database objects** (via Railway Postgres shell):
   ```sql
   SELECT COUNT(*) FROM ai_usage;             -- 0 initially
   SELECT COUNT(*) FROM ai_usage_analytics;   -- 0 initially; view must exist
   ```

---

## Deploy-environment invariants

These hold for the current Railway topology. If you change the edge/proxy setup (custom CDN, an added reverse proxy, Railway networking changes), re-verify them — nothing fails a test if they break.

- **Public endpoint rate-limiting depends on the edge setting `X-Real-IP`.** The unauthenticated `/public/*` routes have no user context, so their only abuse control is a per-IP rate limiter. It keys on `X-Real-IP` (edge-set, spoof-resistant), falling back to the client-settable `X-Forwarded-For` — so if the edge ever stops setting `X-Real-IP`, the limit silently degrades to a forgeable header. After deploy, confirm the limiter resolves the true client IP from `X-Real-IP` (the post-deploy verification tracked in the public-view plan and `docs/architecture.md` §17). See `core/request_utils.py` for the resolution order.

---

## Customizing Domain URLs

Railway generates random subdomains like `frontend-production-fb79.up.railway.app`. To customize:

### Change Railway Subdomain

1. Click on a service → **Settings** → **Networking**
2. Click the **edit icon** (pencil) next to the generated domain
3. Change the subdomain (e.g., `my-bookmarks` → `https://my-bookmarks.up.railway.app`)
4. Click **Save**

### Use a Custom Domain

See [docs/custom-domain-setup.md](docs/custom-domain-setup.md) for detailed instructions on configuring a custom domain with DNS (its identity-provider steps are the historical Auth0-era record — the Clerk equivalents are the DNS records in Step 6b and the origin settings below).

Quick summary:
1. Add custom domain in Railway (each service → **Settings** → **Networking** → **+ Custom Domain**)
2. Add CNAME records at your DNS provider
3. Update Railway environment variables (`CORS_ORIGINS`, `VITE_API_URL`, etc.)
4. Update `CLERK_AUTHORIZED_PARTIES` on the api/cron services to the new origin
5. Redeploy all services

**Important:** After changing any domain, update:
- `CORS_ORIGINS` on the **api** service (must include `https://`)
- `CLERK_AUTHORIZED_PARTIES` (api + cron services) and the Clerk instance's domain/DNS records (Step 6b)
- **Redeploy the frontend** if you changed the API URL - Vite bakes `VITE_API_URL` at build time, so a rebuild is required for changes to take effect

---

## Deploying Changes

Push to `main` branch - Railway auto-deploys from connected GitHub repo.

For manual deploy:
```bash
railway up -s api         # Deploy API
railway up -s frontend    # Deploy frontend
railway up -s content-mcp # Deploy Content MCP
railway up -s prompts-mcp # Deploy Prompt MCP
```

---

## Running Migrations

Migrations run automatically via the pre-deploy command configured in Step 4 (API Service).

To run migrations manually (if needed):
1. Go to Railway dashboard → **api** service → **Settings** → **Deploy**
2. The pre-deploy command `uv run alembic upgrade head` runs before each deployment

---

## Viewing Logs

```bash
railway logs -s api
railway logs -s frontend
railway logs -s content-mcp
railway logs -s prompts-mcp
```

Or use Railway dashboard → Click service → **Logs** tab

---

## Troubleshooting

### Build fails

Check build logs in Railway dashboard. Common issues:
- Missing dependencies in `pyproject.toml`
- Wrong root directory for frontend

### Database connection fails / ModuleNotFoundError: psycopg2

1. Verify `DATABASE_URL` uses `postgresql+asyncpg://` prefix (NOT `postgresql://`)
2. Do NOT use `${{Postgres.DATABASE_URL}}` - you must manually copy and modify the URL
3. See Step 5 above for detailed instructions

### CORS errors

Verify `CORS_ORIGINS` on API service includes your frontend domain with `https://`

### Frontend shows blank page

Check browser console. Verify `VITE_API_URL` points to your API's Railway domain.
