# AGENTS.md

Tiddly — a multi-tenant SaaS for managing bookmarks, notes, and prompt templates. Monorepo: FastAPI backend, React frontend, Go CLI, Chrome extension, and two MCP servers for AI agent integration.

**For a system-level overview** (how services, databases, crons, MCP servers, CLI, and external deps fit together), see [`docs/architecture.md`](docs/architecture.md). This file is for conventions and rules; the architecture doc is for shape.

## Commands

Run `make help` or see the `Makefile` for all targets. Key commands:

```bash
make backend-verify       # lint + tests (always run before backend PRs)
make frontend-verify      # lint + typecheck + tests
make cli-verify           # lint + tests
make tests                # full suite across all components
make migration message="description"  # create new Alembic migration
```

**Run a single backend test:**
```bash
PYTHONPATH=backend/src uv run pytest backend/tests/path/to/test_file.py::test_name -v
```

**Run a single frontend test:**
```bash
cd frontend && npx vitest run src/path/to/file.test.ts
```

**Dev environment in a fresh checkout/worktree:** secondary checkouts start bare — before dev servers will run you likely need: (1) `.env` at the repo root — copy it from the primary checkout (`~/repos/bookmarks/.env`); it's gitignored and holds local config including `CORS_ORIGINS`. (2) `cd frontend && npm ci`. (3) Postgres + Redis via `make docker-up` — but check `docker ps` first: the containers are shared per-machine, so the primary checkout's instances (ports 5435/6379) serve every checkout and are usually already running. The Python venv creates itself on first `uv run`/`make api-run`.

**One API, one frontend per port — and CORS is read at startup:** only one API can hold port 8000; an instance from another checkout serves fine when your branch has no backend changes. But `CORS_ORIGINS` is read once at startup (`--reload` watches code, not `.env`) — if the frontend runs on a port the running API predates (e.g. a worktree's frontend on 5174), API calls fail as axios "Network Error" despite a healthy `/health`. Fix: ensure the port is in `CORS_ORIGINS`, then restart the API.

**Leaving dev servers running for the user (agents):** any process an agent launches through its shell — including "background" tool modes — is killed when the agent's session ends. If the user needs a server still running after you're done (e.g. for manual testing), launch it **detached** with output to a log file:

```bash
# Frontend (pin the port — another checkout's dev server may hold 5173)
cd frontend && nohup npm run dev -- --port 5174 --strictPort > /tmp/tiddly-frontend.log 2>&1 & disown
# Backend API
nohup make api-run > /tmp/tiddly-api.log 2>&1 & disown
```

Then verify it responds (`curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/`) before handing the user a URL, and tell them the actual port, the log path, and how to stop it (`kill $(lsof -t -iTCP:<port>)`). Check first whether a server is already up — port 8000 or 5173 already listening usually means another checkout's instance is running and may serve fine (the API does, when the branch has no backend changes).

## Architecture

### Backend (`backend/src/`)
- **FastAPI + async SQLAlchemy 2.0 + PostgreSQL 17** (pgvector). Python 3.13, deps managed by `uv`.
- **PYTHONPATH is `backend/src`** — all imports relative to this root (e.g., `from api.routers import bookmarks`, `from services.bookmark_service import BookmarkService`). Never use `from backend.src...` or relative imports.
- **Entry point**: `api/main.py`. Routers in `api/routers/`, services in `services/`, models in `models/`, schemas in `schemas/`.
- **`BaseEntityService`** provides shared CRUD for bookmark/note/prompt services. `ContentService` handles unified cross-type search. `LLMService` wraps LiteLLM for multi-provider AI.
- **Auth** (`core/auth.py`): Clerk-issued JWTs (session tokens + OAuth access tokens; Clerk is the sole accepted issuer — see `docs/architecture.md` §5) plus Personal Access Tokens (`bm_` prefix). Dev mode bypass via `VITE_DEV_MODE=true`. Cached in Redis (5-min TTL).
- **Inbound webhooks** (`api/routers/webhooks.py`): Clerk delivers `user.deleted` (Svix-signed) to `POST /webhooks/clerk` — signature verified on the raw body before anything else; deletion = identity tombstone (blocks JIT resurrection) + cascade delete + auth-cache invalidation. Fails closed (503) without `CLERK_WEBHOOK_SIGNING_SECRET`.
- **Models**: UUIDv7 PKs, soft delete (`deleted_at`), archiving (`archived_at`), trigger-maintained FTS vectors.

### Frontend (`frontend/src/`)
- React 19 + TypeScript + Vite + Tailwind CSS 4. Node v22 (`.nvmrc`).
- State: Zustand (`stores/`). Data fetching: @tanstack/react-query (`hooks/`). Routing: React Router v7. Editor: Milkdown.
- **Public content is single-sourced and agent-readable** (`content/`): docs/legal prose as markdown (`content/prose/*.md`, rendered via `react-markdown` — not MDX, no SSR) and structured data as JSON the code reads (`content/data/*.json`: FAQ, known issues, tips, tiers). A Vite plugin serves both verbatim as static files at `/prose/*.md` and `/data/*.json` (each with a generated `index.json` manifest), so non-JS clients can read them; the `Docs*.tsx` pages are thin renderers of the prose. See `docs/implementation_plans/2026-05-21-content-as-markdown.md`.
- Other static data in `data/` — `tips/` (loader + selectors + validation over `content/data/tips.json`), `docsRoutes.tsx`/`settingsRoutes.tsx` (command-palette keyword indexes). Keyboard shortcuts are a validated JSON source at `shortcuts/shortcuts.json` (the loader derives OS-agnostic display tokens; `utils/platform.ts` localizes them at render — Mod → ⌘ on Mac, Ctrl elsewhere). JSON data files are schema-validated at load.

### MCP Servers
- **Content MCP** (`backend/src/mcp_server/`, port 8001): bookmarks/notes CRUD and search.
- **Prompt MCP** (`backend/src/prompt_mcp_server/`, port 8002): prompt template management.
- Both proxy through the backend API (require API server on port 8000).

### CLI (`cli/`)
- Go + Cobra + Viper. Browser-based OAuth login (authorization code + PKCE, loopback listener) + keyring credential storage; PATs for headless use.
- `tiddly ai-instructions` is the zero-auth, agent-first command: it fetches the hosted `llms-cli-instructions.txt` from the web origin (`config.WebURL()`, default `https://tiddly.me`) and prints it, with a minimal `const` fallback on fetch failure (exits 0). It's excluded from the `PersistentPreRunE` init/update-check in `root.go` (no side effects).

### Chrome Extension (`chrome-extension/`)
- Bookmark saver popup + background service worker. Manifest V3.
- **Auth**: syncs with the tiddly.me web session (Clerk Sync Host) — a live session wins, a stored PAT is the fallback; resolution and tokens live only in the background worker (`auth.js`), pages get status + an opaque principal via `GET_AUTH_STATUS`. All user-derived local caches are namespaced per account (`cache-ownership.js`) and every data request is bound to its expected principal, fail-closed.
- **The loadable artifact is built, not the source tree**: `node build.mjs <development|production>` (or `make chrome-ext-build` for both) bundles the service worker with esbuild (`format: 'esm'`, paired with the manifest's `"type": "module"`), copies static files, and generates the per-environment `manifest.json` from `manifest.base.json` into `build/<mode>/`. Config (API URL, Clerk publishable key, sync host, Frontend API origin) is injected at build time — overrides via gitignored `.env.<mode>.local` files (see `.env.template`). `make chrome-ext-zip` ships a clean production build only; `test/build.test.js` asserts the artifact contents.

## Key Patterns

- **Multi-tenant**: All queries scoped to authenticated user via `user_id`.
- **Subscription tiers**: FREE, STANDARD, and PRO with different rate limits and quotas — always test tier gating for AI features. `Tier.DEV` also exists as a runtime-only tier resolved when `VITE_DEV_MODE=true`.
- **Rate limiting**: In-memory with Redis fallback, per-user and per-operation.
- **ETag caching**: HTTP 304 responses for unchanged content.
- **Content versioning**: `ContentHistory` tracks changes with diff-match-patch.
- **SSRF protection**: URL scraping validates against internal networks.
- **Background tasks** (`backend/src/tasks/`): `ai-usage-flush` (hourly) and `cleanup` (daily) are deployed as Railway cron services. `orphan-relationships` is implemented and tested but intentionally deferred at beta scale — see [KAN-67](https://tiddly.atlassian.net/browse/KAN-67). See `docs/architecture.md` §9 for details.

## Evals (`evals/`)

LLM-based evaluations for agentic tool behavior. Currently covers MCP servers; expanding to AI suggestion endpoints. Run with `make evals` (requires API + MCP servers running). After modifying MCP tools or AI endpoints, run relevant evals to catch regressions.

## Design Docs (`docs/`)

`docs/implementation_plans/` contains dated plans for past and in-progress features. `docs/` also has high-level design documents (e.g., `ai-integration.md`, `content-versioning.md`, `connection-pool-tuning.md`). **Before designing a new feature or refactoring a system, check `docs/` for existing plans and design decisions.**

## Security Tests (`backend/tests/security/`)

Includes SSRF tests (run locally) and live penetration tests (`deployed/test_live_penetration.py`) that run against production. **After changes to auth, API endpoints, or input validation, update these tests and remind the user to run the deployed security tests against production.**

## Don't

- **Don't create migrations manually** — always use `make migration message="..."`.
- **Don't add `@pytest.mark.asyncio`** — `asyncio_mode = "auto"` is set in `pyproject.toml`.
- **Don't use `pip`** — use `uv`. Run commands via `uv run` (e.g., `uv run pytest`).
- **Don't mutate `deleted_at`/`archived_at` directly** — use the service layer methods.
- **Don't use synchronous DB calls** — all database access is async.
- **Don't bypass auth outside dev mode** — `VITE_DEV_MODE=true` is for local development only.
- **Don't commit/push without approval**

## Files to Keep in Sync

After any feature, API, pricing, or UI change, review whether these need updating:

**Public content — edit the single source, not the renderer:**
- Docs/legal prose: `frontend/src/content/prose/*.md`. The `docs/Docs*.tsx` pages and the legal pages (`PrivacyPolicy.tsx`/`TermsOfService.tsx`, which add only page chrome + the dynamic "Last Updated" date) are thin renderers of these — editing the `.tsx` won't change the content (or what's served at `/prose/*.md`).
- FAQ: `frontend/src/content/data/faq.json` (one file feeds both `DocsFAQ` and `SettingsFAQ` via `components/FAQContent.tsx`). Known issues: `content/data/known-issues.json`. Tips: `content/data/tips.json`.
- Changelog: `frontend/src/content/data/changelog.json`. Roadmap: `content/data/roadmap.json`. The `changelog/Changelog.tsx` and `roadmap/Roadmap.tsx` pages are thin renderers — editing the `.tsx` won't change the content (or what's served at `/data/*.json`); presentation-only bits (tag/accent colors) stay in the renderer.
- Keyboard shortcuts: `frontend/src/shortcuts/shortcuts.json`.
- Tier limits / pricing numbers: `frontend/src/content/data/tiers.json` — the single cross-stack source (backend enforcement + `Pricing.tsx` display + served `/data/tiers.json`). **Never re-hardcode tier numbers**; `Pricing.tsx` reads them from this file (a test guards against drift).

**AI data-handling disclosure — the privacy policy makes claims the code has to keep true:**
- `frontend/src/content/prose/privacy.md`'s "AI Features" section states both **what** is sent to LLM providers and **what triggers** a request. Both halves drift independently, and both have drifted before — the section once described the features as "not yet implemented," and its replacement then described them as click-triggered when the tag and linked-content controls actually fire on open.
- Review it whenever you change: **payload** — `services/llm_prompts.py` (the canonical source for what each prompt carries), `services/llm_service.py`'s provider/model list, or any `/ai/*` endpoint; or **trigger** — the suggestion hooks (`hooks/useTagSuggestions.ts`, `useMetadataSuggestions.ts`, `useRelationshipSuggestions.ts`, `useArgumentSuggestions.ts`), their `hooks/useAI*Integration.ts` wiring counterparts (which decide *when* a request fires — tag and relationship fire on open; metadata and argument fire per click), or the components wiring them (e.g. `components/ContentCard/actions/AddTagAction.tsx`).
- The policy deliberately describes **categories**, not an exhaustive field list, so ordinary prompt edits don't invalidate it — but a new *kind* of data (a new identifier, a new related-content source) or a change in *when* a request fires does. Over-disclosing is safe; under-disclosing is the defect.

**Designed pages still authored in TSX** (`frontend/src/pages/`):
- `LandingPage.tsx`, `FeaturesPage.tsx` (marketing layouts — prose intentionally not migrated to markdown; see the content-as-markdown plan's M4), `Pricing.tsx` (layout and qualitative copy; the *numbers* come from `tiers.json`).

**LLM/AI discoverability — the agent-empowerment artifact family** (`frontend/public/`, served at the web origin):
- `llms.txt` — the hub: value prop, concepts, pricing *summary*, and the index to everything else. An agent's first stop.
- `llms-app-usage.txt` — operating the app (search/organize/edit/lifecycle + the gotchas to flag).
- `llms-integration.txt` — connecting AI tools (MCP servers, skills, REST API + PAT, the session-only 403 surfaces, the per-tool prompt-consumption model).
- `llms-cli-instructions.txt` — the `tiddly` CLI deep-dive (the doc `tiddly ai-instructions` fetches and prints).
- **Anti-drift rules for the family** (keep these or it rots): generic facts (value prop, tiers/pricing, concepts) live **once**, in `llms.txt`; subfiles cross-reference rather than restate, and each goes deep only on its own job. For any inlined code-derived fact (tier numbers, command/tool names, URLs, the 403 surfaces), the file's header names the canonical source to diff against — and prefer **linking** the now-fetchable artifact (`/data/*.json`, `/prose/*.md`) over inlining. Use absolute `https://tiddly.me/...` URLs so references resolve when quoted out of context. Design + rationale: `docs/implementation_plans/2026-05-23-agent-empowerment.md`.
- **In-app agent-prompt copy** lives in `frontend/src/data/agentPrompts.ts` (the ready-to-paste prompts behind the `AgentPromptButton`/`AgentPromptCard` CTAs on the landing/features pages, the AI-integration setup widget, and the first-run empty state). Same anti-drift rule: these prompts must **point at** the hosted artifacts (`llms.txt`, `llms-app-usage.txt`, `llms-cli-instructions.txt`) and tell the agent to read them — **not restate code-derived per-tool facts** (e.g. which tools use skills vs. tools-only; the canonical source is the CLI's `validSkillsTools` + `llms-integration.txt`). Restating such a fact here once drifted (Antigravity wrongly described as using skills); keep the copy deferential.

**Command palette search index:**
- `frontend/src/data/docsRoutes.tsx` — hand-curated keyword summaries that make `/docs/*` pages findable via the command palette. When you add a docs page, add its entry (path + label + keyword-rich `searchText`). When you substantially change an existing docs page (new sections, renamed concepts, removed features), update its `searchText`.
- `frontend/src/data/settingsRoutes.tsx` — same shape and obligation for `/app/settings/*` pages. The motivating case: searching `mcp` should surface `Settings: AI Integration` (where MCP is configured) even though the literal label doesn't contain that term.
- Optimize both for keyword density, not prose — terms a user might search for when looking for that page. Drift is graceful (a missing keyword means a missed result, not a broken feature), but accumulating drift erodes palette discoverability over time.

**Project-level docs:**
- `README.md` — feature list and setup instructions.
- `.env.example` — when adding/removing/renaming environment variables.
- `AGENTS.md` — when build commands, architecture, conventions, or project structure change.
- `docs/architecture.md` — when services, crons, middleware, auth variants, tier definitions, Redis key schemas, CLI commands, or other architecture changes occur. Of note, see the following sections for commonly missed updates:
    - "Known drift risks" section for the areas most likely to need updating
    - "Things that are easy to miss" section for non-obvious invariants to add to when you learn one.
- `README_DEPLOY.md` — when Railway service topology, env vars, or post-deploy steps change.
