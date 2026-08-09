# MCP OAuth connector verification — working notes (2026-07-16)

Raw observations from the connector verification ladder (the OAuth phase of the
[Clerk migration plan](2026-07-02-clerk-migration.md)). These notes feed the user-facing
docs (Settings → AI Integration, per-client instructions, `llms-integration.txt`) — the
UI paths below are **as observed on the recorded date**, and connector UIs move around,
so treat the docs derived from them as the maintained artifact and this file as evidence.

Server URLs (what users paste):
- Content (bookmarks + notes): `https://content-mcp.tiddly.me/mcp`
- Prompts: `https://prompts-mcp.tiddly.me/mcp`

## Verified end-to-end

| Client | Path observed | Result |
|---|---|---|
| MCP Inspector (dev, localhost) | Transport "Streamable HTTP" → URL → Connect; leave Client ID/Secret/Scope empty (empty = DCR); default localhost redirect accepted by Clerk dev | ✅ both servers, real tool calls |
| MCP Inspector (prod) | Same against prod URLs | ✅ both servers |
| Claude (web, claude.ai) | Settings → Connectors → Add custom connector → name + paste URL → OAuth sign-in/consent → enable connector in chat | ✅ content server, real tool calls (pulled notes/bookmarks) |
| `tiddly` CLI OAuth login | Unchanged flow; now shows a consent screen (forced by enabling DCR instance-wide) | ✅ |
| Codex CLI (v0.144.4) | `codex mcp add tiddly-content --url https://content-mcp.tiddly.me/mcp` — auto-detects OAuth and launches the browser flow immediately (no separate `codex mcp login` needed). Config is **global** (`~/.codex/config.toml`); remove with `codex mcp remove <name>` | ✅ content server, first try — no patch needed |
| Claude Code CLI | `claude mcp add --transport http -s user tiddly-content https://content-mcp.tiddly.me/mcp` (and same for `tiddly-prompts`; `-s user` = global, default `local` = per-directory), then `/mcp` → Authenticate per server (browser flow, persists across projects) | ✅ BOTH servers, real tool calls — the prompts server's first non-Inspector OAuth client |
| Claude Desktop / iOS | No per-device setup: custom connectors are **account-level** — a connector added on web appeared in Desktop, and one added *from Desktop* (prompts server) appeared on claude.ai and the iOS app, OAuth grant intact | ✅ both directions of sync; prompts connector added via Desktop |

## ChatGPT — ✅ works, but ONLY with an operator-side patch per registration

> **Superseded 2026-08-09** — OpenAI fixed the missing-`openid` bug; fresh ChatGPT
> connections now work with no patch. See "2026-08-09 addendum" below. Kept as recorded
> for the diagnosis evidence.

- **Path observed (2026-07-16, chatgpt.com web, Pro plan):** Settings → **Plugins → Browse
  Plugins → "+" icon** → name + paste URL. (No "Apps & Connectors" section and no
  Developer-mode toggle was needed, contrary to older docs.) The ChatGPT **desktop app has
  no connector management UI** — use the web.
- **Failure + root cause (verified 2026-07-16):** clicking "Sign in with <connector name>"
  popped a window that instantly bounced back to "There was a problem connecting … Try again
  later." Root cause is a **known, OpenAI-acknowledged ChatGPT bug (open since Dec 2025)**:
  ChatGPT's DCR registration omits the `openid` scope (`email offline_access profile`),
  but its authorize request *demands* `openid` — Clerk correctly rejects the
  scope-vs-registration mismatch and error-redirects before any sign-in/consent renders.
  (Claude's registration includes `openid`; that was the one meaningful diff.) Refs:
  https://community.openai.com/t/missing-openid-scope-in-dynamically-registered-oauth-clients/1368690
- **Diagnosis evidence:** our logs showed discovery working (401 → metadata 200); Clerk
  showed successful DCR per attempt; direct authorize probes with ChatGPT's client_id passed
  every request-shape test (scope variants, no-PKCE, RFC 8707 `resource`) — isolating the
  failure to scope-vs-registration validation deeper in the flow.
- **Fix applied (one line per registration, prod Clerk, user-approved):**
  `clerk api /oauth_applications/<id> --instance prod -X PATCH -d '{"scopes":"openid email profile offline_access"}'`
  After patching, the same connector connected and ran real tool calls. ✅
- **Operational implication (open decision):** every NEW ChatGPT connector registration —
  any other user, or even the same user adding the prompts server — is born broken and
  needs this patch until OpenAI fixes their bug. Self-serve ChatGPT onboarding does not
  currently work. Options: document as a known issue; patch-on-request; a periodic sweep
  that adds `openid` to ChatGPT-named registrations missing it; or an operator alert on
  new DCR registrations.

## Codex vs ChatGPT — same company, different OAuth clients

Codex CLI's observed authorize request registers and requests a **consistent** scope set
*including* `openid` (plus PKCE S256, loopback redirect, and the RFC 8707 `resource`
parameter). So the missing-`openid` bug is specific to ChatGPT's connector client, not
OpenAI's OAuth stack generally — Codex needs no operator-side patch.

## Observations that feed other docs

- Clerk consent screen displays the **client-chosen name** — client identity should be
  verified via the registered redirect URI (provider-owned domain), which is readable via
  `clerk api /oauth_applications` (see the ledger's MCP section, "As-executed observations").
- DCR registers **one OAuth application per connection attempt** (Claude registered twice
  for one add; ChatGPT once per retry) — entity accumulation is expected; periodic cleanup
  via `DELETE /oauth_applications/{id}` is the documented response.

## 2026-08-09 addendum — `scopes_supported` deployment + re-verification

Context: tiddly PR #169 deployed `scopes_supported: ["openid", "offline_access"]` in both
servers' RFC 9728 protected-resource metadata (rationale in `shared/mcp_oauth.py`). This
round verified the deploy per that PR's fresh-registration matrix. Registration evidence
below read via `clerk api /oauth_applications --instance prod` (note: the endpoint
paginates at 10 by default — pass `limit` or counts mislead).

### Fresh-registration results

| Client | Result | Registration observed |
|---|---|---|
| Claude Code CLI (localhost + Clerk dev, pre-merge) | ✅ full flow + tool calls | `offline_access openid` — derived from the published metadata; authorize request matched (`scope=openid+offline_access`, PKCE S256, RFC 8707 `resource` incl. path) |
| Claude Code CLI (prod, fresh registration) | ✅ full flow + tool calls | `offline_access openid` (pre-deploy default was `email offline_access profile`) |
| Claude connector (web/desktop, remove + re-add) | ✅ tool calls | `offline_access openid` — previously registered the full AS list incl. `private_metadata`/`public_metadata`; the over-asking is gone |
| ChatGPT **desktop** (2026-08-09 path: Settings → Plugins → Add → Add MCP Server; name + **Streamable HTTP** + URL, token blank → Save; then Plugins → MCPs → **Authenticate**) | ✅ **no operator patch**, real content access | Registers as **"Codex"** with `email offline_access openid private_metadata profile public_metadata` — the AS-metadata fallback, now *including* `openid` |

### Findings

- **ChatGPT is fixed on OpenAI's side, not by our metadata.** Its registration now
  includes `openid` (the July root cause) but ignores our published `scopes_supported`
  (it registered the authorization server's full list). So the known issue is retired
  because OpenAI shipped their fix; publishing `scopes_supported` was not the operative
  change for ChatGPT. The per-registration `clerk api … PATCH` workaround is obsolete for
  new registrations. Also contrary to the July note, the **desktop app now has connector
  management UI**.
- **Anthropic clients (Claude Code and the Claude connector) derive both registration and
  authorize scopes from `scopes_supported`** — the minimal-grant outcome the PR aimed for,
  confirmed in prod for both codebases.
- **One-time migration edge, observed then remedied:** an interactive re-auth on a
  *pre-deploy* Claude Code registration failed with `invalid_scope` ("not allowed to
  request scope 'openid'") — stale registration without `openid` + metadata-derived
  authorize. Remedy verified: clear auth → reconnect (fresh registration). Only
  registrations lacking `openid` are exposed (pre-deploy Claude/Codex/ChatGPT ones all
  include it; requesting a subset of registered scopes is allowed). Refresh-token renewals
  never hit the authorize endpoint, so working connections are unaffected until an
  interactive re-auth. Pre-deploy `antigravity-client` registrations (`email offline_access
  profile`) carry the same exposure.
- **Not re-verified this round:** Codex CLI and MCP Inspector fresh registrations (July
  evidence stands; Codex's client already registered a consistent set incl. `openid`).
  Clerk matching loopback redirects across *differing* ports remains unobserved — every
  successful flow used a registration whose redirect port matched.
