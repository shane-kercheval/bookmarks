# CLI Agent Testing Procedure

End-to-end verification of the `tiddly` CLI. Structured for an AI agent to execute against a **local** dev environment.

Each test describes a **behavioral claim**. You decide how to verify it — write whatever shell / `jq` / `uv run python3` / filesystem checks fit your environment.

**Every bash snippet in this document is a suggestion, not a mandate.** Phase 0's setup block, Phase 9's teardown block, the `tokens create` fixture in T5.8c, the `jq`-filter-and-sort compare in T6.6/T6.7 — these are illustrative of HOW to accomplish the goal described in prose. They are **not** the test. The test is the behavioral claim. The shell is a means to verify it.

If a suggested command fails in your environment (wrong shell idiom, missing tool, output format that differs from what the doc assumed, regex that doesn't match, etc.), your job is to **adapt your approach and carry on** — not to halt because the example didn't run. See [§ When something goes wrong](#when-something-goes-wrong) for how to distinguish that case from a genuine product-behavior mismatch.

## Runs against LOCAL test services ONLY

```
TIDDLY_API_URL=http://localhost:8000
TIDDLY_CONTENT_MCP_URL=http://localhost:8001/mcp
TIDDLY_PROMPT_MCP_URL=http://localhost:8002/mcp
```

Phase 0 aborts if these aren't set. The tokens this procedure mints live only on the local dev server. The user's **real config files** on disk (`~/.claude.json`, Claude Desktop config, `~/.codex/config.toml`) are reused — Phase 0 backs them up, sanitizes them, and Phase 9 restores the originals. Everything between Phase 0 and Phase 9 is a reversible mutation of real files. Treat the backup directory accordingly.

---

## When something goes wrong

There are two very different "something went wrong" cases. Treat them differently.

### Case A: a suggested command didn't work — adapt and continue

If a snippet in this document doesn't produce what the prose says it should — but the issue is with the **snippet**, not the product — adapt your approach and keep going. This is the expected path, not an error condition. The most common reasons:

- Your shell (zsh vs bash) parses an idiom differently.
- A tool the example assumed (`jq`, `awk`, `uv run python3`) is on a different version or absent.
- The CLI's output format shifted slightly in a way that doesn't contradict the claim (e.g. extra whitespace, a new line that doesn't affect meaning).
- The example has a regex typo or shell-quirk bug (zsh `$var[...]` subscript, `grep -q` under `pipefail`, a missing `--` option terminator).
- The suggested setup step doesn't compose cleanly with the state left by a previous test.

In any of these, adapt: verify the claim a different way. Dump the raw observation, understand what the actual behavior is, write a different check. Your strength is exactly this kind of local reasoning.

**Concrete example.** Say T2.7 suggests asserting `jq -e '.mcpServers.tiddly_notes_bookmarks.args | index("mcp-remote")' $CLAUDE_DESKTOP_CONFIG`, and `index` returns `null` on your config because `args` is shaped differently than the doc assumed. You check with `jq '.mcpServers.tiddly_notes_bookmarks.args' $CLAUDE_DESKTOP_CONFIG` and see `args` does contain `"mcp-remote"` — just not as a top-level string. Switch to `jq -e '.mcpServers.tiddly_notes_bookmarks.args | any(.[]?; . == "mcp-remote")' ...` and continue. Log:

```
- T2.7 PASS (adapted: jq index → any(.[]?;) for nested-array shape)
```

This is a signal, not a failure. It tells the engineer where the procedure's suggested shell is unreliable or outdated so they can tighten it.

**SKIP variant — inconclusive after fair adaptation.** When a test genuinely can't be verified — not because the product misbehaves, but because the local environment or dev DB doesn't have the preconditions (e.g. T6.6 where no prompts in this dev DB match the required tags) — log `- T<id> SKIP (adapted <n> ways, inconclusive — <one-line reason>)`. **SKIP is never an alternative to Case B.** If you have any evidence the product behavior contradicts the claim, report Case B regardless of how many adaptations you've tried. SKIP is narrowly for "the test can't meaningfully fire in this environment."

If your adaptation reveals that the product actually **does** misbehave (the different approach also fails, for the same observable reason), that's Case B below.

### Case B: the product's behavior contradicts the claim — stop and report

When, after fair effort to verify it, the CLI's observable behavior contradicts the test's **behavioral claim** — that is the signal this procedure is designed to surface. Do the following:

1. **Stop.** Do not run any cleanup, restore, or token-revocation step. Do not move to the next test. Do not adapt the **claim** itself — the claim is the test; rewriting it to match the product defeats the purpose.
2. **Report.** Append a structured block to `$REPORT`:
   - Test ID.
   - The claim in your own words.
   - What you actually observed — command you ran, exit code, relevant output (paraphrased, never a raw Bearer value).
   - Category: **product-bug** (CLI's behavior is wrong), **plan-bug** (the claim is outdated or the test is mis-specified), **environment** (API down, auth died, permission issue), **ambiguous** (not enough evidence to classify).
   - A one-sentence hypothesis if you have one.
3. **Wait** for the engineer. They'll decide whether this is a real bug, a plan update, or something you should retry.

### Before you report under Case B, sanity-check

- **Did you understand the claim correctly?** Re-read the test prose.
- **Did you rule out a snippet issue?** Under Case A, you should have already tried a second approach. If multiple reasonable ways to verify the claim all independently show the product doing something different from what the claim says, that's a real product-vs-claim mismatch.
- **Is it environmental?** `bin/tiddly auth status` and `bin/tiddly status` — if auth died or the API is down mid-run, that's environment, not a product bug.

If you still can't tell between product-bug and plan-bug on the evidence you have, mark **ambiguous** and report. Don't guess.

### There is intentionally no automatic destructive recovery

A mismatch is almost always (1) a product bug to investigate with the state preserved, (2) a plan bug to adjust, or (3) a snippet-authoring issue you've already worked around under Case A. None of those want a full session wipe. Preserve state; wait for the engineer.

---

## Never echo plaintext Bearer values

The only place plaintext PAT values should ever surface is from the explicit `tiddly tokens create` path, and those must be consumed immediately (piped into a config mutation, assigned to a shell variable that is `unset` right after use). Specifically:

- **Never** `cat`, `head`, `tail`, `less`, or `grep -o 'Bearer .*'` on a config file. Use `jq -e` / `tomllib` with exit-code assertions that don't print values.
- **Never** include raw config contents or Bearer values in your report. If what you want to report is token-bearing, hash it, name it (the `cli-mcp-*` name), or cite the first 12 characters of the PAT prefix (safe — that's what `tokens list` shows) instead of the full value.
- **Never** `set -x` around a block that has a captured PAT — it echoes every assignment including the token.
- On any `configure` / `remove` / `dry-run` output you're about to echo, call `assert_no_plaintext_bearers "$out" "T<id>"` from `lib.sh` first. It FATALs if a raw Bearer slipped through the CLI's redactor. If it fires, that **is** the finding — report it and stop.

---

## Prerequisites

- CLI binary built: `make cli-build` produces `bin/tiddly` at the repo root.
- Local API + MCP servers running on their default ports (8000 / 8001 / 8002).
- **Python invocations go through `uv run`**: the project manages its Python environment with `uv`, not system `python3`. When a test needs Python (most often for TOML parsing via stdlib `tomllib`), prefer `uv run python3 -c '...'`. Bare `python3` will sometimes work (stdlib-only) but is stylistically inconsistent with the rest of the repo and can hit version drift on machines where system python lags the uv-managed one.
- Backend `VITE_DEV_MODE=false`. Dev mode short-circuits PAT validation and silently breaks tests that depend on server-side token checks (T2.12 canonical reuse, T5.8 canonical revoke, T5.8d orphan filter). Phase 0 has an explicit probe; failing that probe means fix dev mode and re-run Phase 0.
- OAuth session alive via `bin/tiddly login` — see [§ Auth](#auth-engineer-must-do-this-manually).

---

## Auth (engineer must do this manually)

The agent cannot complete the OAuth device flow (requires a browser). This must be set up **before** the agent is launched.

### Critical — `.env` is NOT read by the CLI

The Go CLI reads **shell environment variables**, not `backend/.env`. Backend/frontend variables in `backend/.env` are invisible to it. If you skip the exports below and run `bin/tiddly login` bare, the CLI falls back to hardcoded **production** defaults and your token ends up being a production token that the local backend will 401 on.

If you already ran `bin/tiddly login` bare and ended up logged into production, run `bin/tiddly logout` first, then start over from step 2.

### Clerk OAuth values — these are not secrets

The Clerk issuer and OAuth client ID are public identifiers (they ship in OAuth URLs), but this repo keeps its development-instance values out of the public tree — supply your own from the dev instance's "Tiddly CLI" OAuth app.

### Paste this block in a fresh terminal

```bash
make cli-build

export TIDDLY_API_URL=http://localhost:8000
export TIDDLY_CONTENT_MCP_URL=http://localhost:8001/mcp
export TIDDLY_PROMPT_MCP_URL=http://localhost:8002/mcp

# Clerk development instance (values outside the repo per the
# no-env-identifiers rule; the client ID is the dev "Tiddly CLI" OAuth app).
export TIDDLY_OAUTH_ISSUER=https://<dev-instance>.clerk.accounts.dev
export TIDDLY_OAUTH_CLIENT_ID=<dev CLI OAuth app client id>

bin/tiddly logout 2>/dev/null || true
bin/tiddly login
bin/tiddly auth status      # should show 'Auth method: oauth' + your dev email
```

Then **launch Claude Code from this same terminal** so the agent's Bash tool inherits these env vars.

---

## Deferred / not-covered-here

These behaviors are verified by Go unit tests (`make cli-verify`), not this procedure:

| Behavior | Test name |
|---|---|
| OAuth tokens revoked after commit-phase write failure | `TestRunConfigure__oauth_commit_failure_revokes_minted_tokens` |
| Revoke failure lists orphan names + first-12 prefix | `TestRunConfigure__oauth_commit_failure_with_revoke_failure_surfaces_orphans` |
| Cleanup context detached from cancelled caller context | `TestRevokeMintedTokens__cancelled_context_fails_every_delete` + `__fresh_context_revokes_cleanly` |
| Backup path surfaced when write fails | `TestRunConfigure__commit_phase_failure_surfaces_backup_path` |
| Backup O_EXCL collision retry preserves both files | `TestBackupConfigFile__collision_retry_preserves_both` |
| Partial-result contract (commit-phase vs. preflight) | `TestRunConfigure__commit_phase_failure_preserves_earlier_writes` + `__preflight_failure_returns_nil_result` |
| classifyServer security invariant (URL wins over name) | `TestClassifyServer__routes_by_url` |
| OtherServer.URL round-trips for mismatch detection | `TestClassifyServer__canonical_name_at_non_tiddly_url_records_url` |
| DeleteTokensByPrefix dedupes by PAT + fans out per-entry | `TestDeleteTokensByPrefix__*` |
| Hard-error ordering in preflight | `TestRunConfigure__hard_error_on_*` |
| `canonicalEntryPATs` rejects cross-wired PATs | `TestRunConfigure__does_not_reuse_pat_from_cross_wired_canonical_slot` |
| `--force` log only fires after PAT resolution succeeds | `TestRunConfigure__force_log_not_emitted_when_pat_resolution_fails` |
| Mismatch error has no double "Error:" prefix under cobra | `TestMCPConfigure__mismatch_error_has_no_double_error_prefix` |

Run `make cli-verify` before this procedure.

---

## Tips for the agent (Bash-per-call model)

The Claude Code Bash tool spawns a fresh shell per call. Functions, variables, and traps from prior calls don't survive. Practical consequences:

- **You (the agent) have memory; the shell does not.** Phase 0 creates a backup directory and a test project directory. Remember these paths and pass them as env exports at the top of every subsequent call. A convenient idiom: begin each call with an `export BACKUP_DIR=...`, `export TEST_PROJECT=...` block listing the paths you need.
- **Source `lib.sh` if you want its helpers in a given call.** It's a small utility file; sourcing is idempotent and side-effect free.
- **Known shell quirks you'll hit on macOS zsh:**
  - `$var[...]` adjacent to `[` is parsed as array-subscript syntax. Use `${var}[...]` or write the value to a file first.
  - `grep -q` inside a pipeline under `set -o pipefail` can exit 141 (SIGPIPE) on large inputs. Prefer `grep PATTERN >/dev/null` or grep against a file.
  - `grep -F "--foo"` treats `--foo` as grep's own flags. Use `grep -F -- "--foo"`.
- **Large CLI output (dry-run diffs can be 100 KB+) is more reliable written to a file than captured into `$(cmd)` and echoed.**
- **Never iterate multi-line command output with `for x in $(cmd)`.** Word-splitting flattens newlines and joins everything into a single argv. Use `while IFS= read -r x; do ...; done < <(cmd)` (or pipe into the loop) instead. This bites `bin/tiddly tokens list | awk '/cli-mcp-/ {print $1}'` and any other multi-row consumer — `for id in $(...)` will silently process the whole token list as one giant ID.

These aren't rules; they're landmines worth stepping around.

---

# Phase 0: Setup

**Behavioral goal:** produce a sandboxed starting state —
 - real configs backed up to a dedicated directory (mode 0700),
 - canonical `tiddly_*` entries sanitized out of live configs so tests never operate on the user's real tokens,
 - pre-existing `cli-mcp-*` token IDs snapshotted for later diff-based cleanup,
 - an empty test-project directory for directory-scope tests,
 - a live markdown report the agent appends to throughout the run.

The block below is a **reference implementation** of the setup. Run it as-is if it works in your environment; adapt it freely if something doesn't (see [§ When something goes wrong](#when-something-goes-wrong)). The behavioral goals above are what matter; the exact bash is one way to reach them. **Remember the `BACKUP_DIR` and `TEST_PROJECT` paths it prints** — you'll export them at the top of every subsequent call.

```bash
set -euo pipefail
source cli/tests_agentic/lib.sh

# ---- 1. Localhost / auth preflight ---------------------------------------
# The CLI falls back to hardcoded production defaults if the engineer
# didn't export TIDDLY_* before launching Claude Code. Check CLI BEHAVIOR
# via `status` / `auth status`, not env vars — the fallback is what we
# actually need to detect.
api_line=$(bin/tiddly status 2>&1 | awk '/^[[:space:]]*URL:/ {print $2; exit}')
case "$api_line" in
    http://localhost:*|http://127.0.0.1:*) ;;
    *)
        echo "FATAL: CLI API URL is '${api_line:-<empty>}', not localhost." >&2
        echo "       Auth/env setup likely didn't happen. Exit Claude Code," >&2
        echo "       paste the § Auth block in a fresh terminal, relaunch." >&2
        exit 1 ;;
esac
auth_out=$(bin/tiddly auth status 2>&1)
grep -E 'Session expired|API error|Not logged in' <<<"$auth_out" >/dev/null && { echo "FATAL: OAuth session not alive."; exit 1; }
grep -E '^User:[[:space:]]+unknown' <<<"$auth_out" >/dev/null && { echo "FATAL: credentials rejected (wrong Clerk instance?)"; exit 1; }

# ---- 2. Dev-mode probe ---------------------------------------------------
# A bogus bm_ Bearer → 401 in prod mode, 200 in dev mode. Dev mode breaks
# PAT-validation tests silently.
dm=$(curl -s -o /dev/null -w '%{http_code}' \
    -H 'Authorization: Bearer bm_devmode_probe_deliberately_invalid' \
    "$TIDDLY_API_URL/users/me")
case "$dm" in
    401|403) echo "Dev-mode probe: backend rejects bogus tokens (good)." ;;
    200)     echo "FATAL: backend is in DEV_MODE (accepted a bogus Bearer). Set VITE_DEV_MODE=false and restart." >&2; exit 1 ;;
    *)       echo "FATAL: dev-mode probe got HTTP $dm from $TIDDLY_API_URL/users/me." >&2; exit 1 ;;
esac

# ---- 3. Platform-specific config paths -----------------------------------
case "$OSTYPE" in
    darwin*) CLAUDE_DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
    linux*)  CLAUDE_DESKTOP_CONFIG="$HOME/.config/Claude/claude_desktop_config.json" ;;
    *) echo "Unsupported OS: $OSTYPE" >&2; exit 1 ;;
esac
CLAUDE_CODE_CONFIG="$HOME/.claude.json"
CODEX_CONFIG="$HOME/.codex/config.toml"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CODEX_SKILLS_DIR="$HOME/.agents/skills"
TIDDLY_BIN="$PWD/bin/tiddly"

# ---- 4. Make the sandbox -------------------------------------------------
BACKUP_DIR=$(mktemp -d); chmod 0700 "$BACKUP_DIR"
TEST_PROJECT=$(mktemp -d)
REPORT="$BACKUP_DIR/test-report.md"
: > "$REPORT"; chmod 0600 "$REPORT"
{
    echo "# CLI Test Run"
    echo
    echo "- Start (UTC): $(date -u +'%Y-%m-%d %H:%M:%SZ')"
    echo "- Platform: $OSTYPE"
    echo "- Git: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)@$(git rev-parse --short HEAD 2>/dev/null)"
    echo "- API: $TIDDLY_API_URL"
    echo "- BACKUP_DIR: $BACKUP_DIR"
    echo "- TEST_PROJECT: $TEST_PROJECT"
    echo
} > "$REPORT"

# ---- 5. Back up real configs + skills dirs --------------------------------
for pair in \
    "$CLAUDE_DESKTOP_CONFIG:$BACKUP_DIR/claude_desktop_config.json" \
    "$CLAUDE_CODE_CONFIG:$BACKUP_DIR/.claude.json" \
    "$CODEX_CONFIG:$BACKUP_DIR/config.toml"
do
    src=${pair%%:*}; dest=${pair##*:}
    [ -e "$src" ] && cp -p "$src" "$dest" && echo "Backed up: $src"
done
[ -d "$CLAUDE_SKILLS_DIR" ] && cp -rp "$CLAUDE_SKILLS_DIR" "$BACKUP_DIR/claude-skills"
[ -d "$CODEX_SKILLS_DIR"  ] && cp -rp "$CODEX_SKILLS_DIR"  "$BACKUP_DIR/codex-skills"

# ---- 6. Snapshot pre-existing <config>.bak.* siblings ---------------------
# Phase 9 will sweep only the delta — siblings that APPEARED during this
# run, not the user's older backups from prior sessions.
for cfg in "$CLAUDE_DESKTOP_CONFIG" "$CLAUDE_CODE_CONFIG" "$CODEX_CONFIG"; do
    find "$(dirname "$cfg")" -maxdepth 1 -name "$(basename "$cfg").bak.*" -type f 2>/dev/null
done | LC_ALL=C sort > "$BACKUP_DIR/siblings-before.txt"
echo "Pre-run CLI sibling backups: $(wc -l < "$BACKUP_DIR/siblings-before.txt") snapshotted."

# ---- 7. Snapshot pre-existing cli-mcp-* token IDs -------------------------
# Later teardown diffs current-vs-snapshot and revokes only the additions.
# A silent `tokens list` failure here would cause every pre-existing token
# to look "new" at teardown; fail loud if it happens.
snap=$(bin/tiddly tokens list 2>&1) || { echo "FATAL: tokens list failed"; echo "$snap" | sed 's/bm_[A-Za-z0-9_-]\{4,\}/bm_REDACTED/g' >&2; exit 1; }
echo "$snap" | awk '/cli-mcp-/ {print $1}' | LC_ALL=C sort > "$BACKUP_DIR/cli-mcp-ids-before.txt"
echo "Pre-run cli-mcp-* tokens: $(wc -l < "$BACKUP_DIR/cli-mcp-ids-before.txt") ids snapshotted."

# ---- 8. Sanitize: strip user's Tiddly entries from live configs -----------
# Two-pass: `mcp remove` for URL-classifier-driven clearing of local entries,
# then hard-strip canonical `tiddly_*` names regardless of URL (catches the
# case where the engineer's real config has canonical-named production
# entries that `mcp remove` leaves alone because they don't match the
# current localhost URL). Originals are in $BACKUP_DIR from step 5.
for tool in claude-desktop claude-code codex; do
    "$TIDDLY_BIN" mcp remove "$tool" >/dev/null 2>&1 || true
done
sanitize_canonical_json "$CLAUDE_DESKTOP_CONFIG"
sanitize_canonical_json "$CLAUDE_CODE_CONFIG"
sanitize_canonical_toml "$CODEX_CONFIG"

# ---- 9. Clear live skills dirs (Phase 6 starts from empty) ----------------
# Backups from step 5 are restored in Phase 9. Clearing now means every
# Phase 6 test runs against a known-empty directory at session start, so
# `skills configure`'s behavior is observable without prior-skill residue
# confounding it. (Stale-skills from earlier T6 tests still apply — T6.6
# and T6.7 have their own per-test wipe.)
rm -rf "$CLAUDE_SKILLS_DIR" "$CODEX_SKILLS_DIR" 2>/dev/null || true

echo
echo "================================================"
echo "Phase 0 ready."
echo "  BACKUP_DIR=$BACKUP_DIR"
echo "  TEST_PROJECT=$TEST_PROJECT"
echo "  REPORT=$REPORT"
echo "  TIDDLY_BIN=$TIDDLY_BIN"
echo
echo "Export these at the top of every subsequent Bash call."
echo "================================================"
```

**After Phase 0, at the top of every Bash call, re-export the paths printed above** (values will differ each run):

```bash
export BACKUP_DIR=<path from Phase 0>
export TEST_PROJECT=<path from Phase 0>
export REPORT=$BACKUP_DIR/test-report.md
export TIDDLY_BIN=$PWD/bin/tiddly
# Config paths — derive from $HOME (same per-OS logic as Phase 0 step 3)
export CLAUDE_CODE_CONFIG=$HOME/.claude.json
export CLAUDE_DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"  # macOS
export CODEX_CONFIG=$HOME/.codex/config.toml
export CLAUDE_SKILLS_DIR=$HOME/.claude/skills
export CODEX_SKILLS_DIR=$HOME/.agents/skills
source cli/tests_agentic/lib.sh    # optional — brings sha_of, assert_no_plaintext_bearers, fixture writers
```

Append a line to `$REPORT` for each test as you go (`echo "- T1.1 PASS" >> "$REPORT"`). On a mismatch, append the structured block from the failure protocol above.

---

# Phase 1: Read-only verification

No mutations, no server-state changes.

### T1.1 — Help surfaces

`bin/tiddly --help`, `mcp --help`, `skills --help` all exit 0 and the output lists the expected subcommands and flags.

- Root help: subcommands `login`, `logout`, `auth`, `status`, `mcp`, `skills`, `tokens`; global flags `--token`, `--api-url`.
- `mcp --help`: subcommands `configure`, `status`, `remove`.
- `skills --help`: subcommands `configure`, `list`.

### T1.3 — `mcp configure --help` content

Exit 0. Help text lists the flags `--dry-run`, `--scope`, `--expires`, `--servers`, `--force`; valid args `claude-desktop`, `claude-code`, `codex`. The help text mentions:

- The CLI-managed entry names (`tiddly_notes_bookmarks`, `tiddly_prompts`) and that other entries are preserved (e.g. the example entry `work_prompts`).
- `--force` as the override for URL-mismatch refusal.
- `.bak.<timestamp>` backup filenames.

It does **not** mention `--yes` / `-y` (removed with the additive-configure rework) and does **not** contain the words "consolidate" / "consolidation" / "migrations from manual setups are safe".

### T1.5 — `status` overview

`bin/tiddly status` exits 0 and its output contains the sections `Tiddly CLI v`, `Authentication:`, `API:`, `MCP Servers:`, `Skills:`. The header is exactly `MCP Servers:` (no `(path: ...)` suffix when `--path` isn't passed). Each detected tool appears; undetected tools are labeled `Not detected`. Any configured row ends with `(<config_key_name>)` in parentheses showing the on-disk entry name.

With `--path "$TEST_PROJECT"`, the header becomes `MCP Servers (path: $TEST_PROJECT):`.

With `--path /nonexistent/path`, the command exits non-zero and the error mentions "does not exist".

### T1.6 — `auth status`

Exit 0. Output contains `Auth method:` (one of `pat` / `oauth` / `flag` / `env`) and `API URL:`.

### T1.7 — `tokens list` output contract

This is a **contract lock** — Phase 0's token snapshot and Phase 9's cleanup both parse `tokens list` assuming the ID is column 1. A silent column reorder or header rename would silently break cleanup.

The header row contains the substrings `ID`, `NAME`, and `PREFIX`, in that order (`NAME` appears before `PREFIX`), plus an `EXPIRES` column (T2.8 depends on that column existing). Column 1 under the header is the token ID.

---

# Phase 2: Configure — happy paths

Starts mutating live config files. The CLI takes `.bak.<timestamp>` sibling backups; Phase 0 also holds originals in `$BACKUP_DIR`.

### T2.1 — claude-code, user scope (default)

`bin/tiddly mcp configure claude-code` exits 0 and:

- Stdout contains `Configured: claude-code`.
- **If** a pre-existing `$CLAUDE_CODE_CONFIG` was present, stdout also contains a `Backed up claude-code config to <path>` line (exact prefix; `<path>` is the `.bak.<timestamp>` sibling the CLI created). That path exists on disk, has the pre-command SHA, and preserves the source's file mode. If no prior config existed, no `Backed up` line is emitted — that's `backupConfigFile`'s documented behavior (`cli/internal/mcp/config_io.go`), not a defect.
- `$CLAUDE_CODE_CONFIG` now has `.mcpServers.tiddly_notes_bookmarks` with `type: "http"`, `url` matching `$TIDDLY_CONTENT_MCP_URL`, and `headers.Authorization` starting with `Bearer bm_`.
- Same for `.mcpServers.tiddly_prompts` at `$TIDDLY_PROMPT_MCP_URL`.
- No pre-existing `mcpServers` key disappeared (diff the key set before/after; only `tiddly_*` keys should be new, everything else unchanged).

**Do the URL / header checks with `jq -e` exit codes, not by printing values.** See [§ Never echo plaintext Bearer values](#never-echo-plaintext-bearer-values).

### T2.2 — `--servers content` preserves prompts

`bin/tiddly mcp configure claude-code --servers content` exits 0. After, both `tiddly_notes_bookmarks` (written) and `tiddly_prompts` (preserved from T2.1) are present in `$CLAUDE_CODE_CONFIG`.

### T2.3 — `--servers prompts` preserves content

Symmetric to T2.2 — both entries present afterward.

### T2.4 — claude-code, directory scope

In `$TEST_PROJECT`, `$TIDDLY_BIN mcp configure claude-code --scope directory` exits 0. `$CLAUDE_CODE_CONFIG` now has both entries under `.projects["$TEST_PROJECT"].mcpServers`. The top-level `.mcpServers` **semantic** content is unchanged — user-scope state wasn't modified.

**Check method:** compare with `jq -S '.mcpServers' "$CLAUDE_CODE_CONFIG"` before vs. after (`-S` sorts keys for stable output). **Don't byte-compare the whole file.** The CLI rewrites the entire config on any write (even directory-scope writes that only touch `.projects[...]`), and Go's `json.MarshalIndent` doesn't preserve the user's original key ordering — so bytes can shift even when no key changed. `jq -S` on the `.mcpServers` subtree gives a stable comparison that reflects semantic intent.

### T2.5 — Codex, user scope

`bin/tiddly mcp configure codex` exits 0, takes a backup of the existing TOML, and writes `[mcp_servers.tiddly_notes_bookmarks]` (with `url = ...` and `[mcp_servers.tiddly_notes_bookmarks.http_headers]` containing `Authorization = "Bearer bm_..."`) and the analogous section for `tiddly_prompts`. Existing non-Tiddly top-level sections are preserved.

**TOML parsing tip:** `uv run python3 -c 'import tomllib; ...'` works on Python 3.11+ (project uses `uv` — see [§ Prerequisites](#prerequisites)). Use exit-code assertions without printing values (same hygiene as JSON).

### T2.6 — Codex, directory scope

In `$TEST_PROJECT`, `$TIDDLY_BIN mcp configure codex --scope directory` creates `$TEST_PROJECT/.codex/config.toml` with both canonical entries. The user-scope `$CODEX_CONFIG` is byte-identical before and after (SHA compare).

### T2.7 — Claude Desktop, user scope

`bin/tiddly mcp configure claude-desktop` exits 0 and writes to the Claude Desktop config a stdio-launcher shape: `.mcpServers.tiddly_notes_bookmarks` has `command: "npx"` and an `args` array that contains `"mcp-remote"`, `$TIDDLY_CONTENT_MCP_URL`, and a `"Authorization: Bearer bm_..."` header arg. Same shape for `tiddly_prompts`. Stderr contains `Warning: Restart Claude Desktop to apply changes.` (note the `Warning:` prefix — configure uses the `ConfigureResult.Warnings` channel).

### T2.8 — `--expires 30` sets expiration ~30 days out

Starting from a clean slate (e.g. `mcp remove claude-code --delete-tokens` first), `bin/tiddly mcp configure claude-code --expires 30` prints `Created tokens: cli-mcp-claude-code-*` (not `Reused`). In `tokens list` the new tokens' `EXPIRES` column holds a date roughly 30 days out (accept a ±1 day window for clock skew).

**Parsing tip:** filter to `cli-mcp-` data rows first, then parse. In a **data** row, EXPIRES is `$5` under default awk (whitespace-splitting): data rows have exactly 6 single-token fields — `LAST USED` is always an ISO date like `2026-05-21` or the em-dash `—`, one token either way. Avoid parsing the **header** row: its `LAST USED` has an internal space that makes `awk` see 7 words, so counting by header position is fragile (the em-dash `—` is also multi-byte UTF-8, so any byte-offset parsing is off).

### T2.9 — Auto-detect

`bin/tiddly mcp configure` (no tool arg) exits 0 and each detected tool's config is updated.

**Output format:** a single comma-joined line — `Configured: <tool1>, <tool2>, <tool3>` (`cli/cmd/mcp.go` joins `ToolsConfigured` with `", "`). Don't grep for `Configured: claude-code` as a substring expecting a per-tool line; grep per tool name with `grep -Fw claude-code` (or similar) against the captured output.

### T2.10 — Status row format after configure

`bin/tiddly status` shows each Tiddly row ending with `(tiddly_notes_bookmarks)` or `(tiddly_prompts)` — the actual config key matches what's on disk. Multiple scopes render cleanly.

### T2.11 — Additive configure preserves non-CLI-managed entries

Headline of the additive-configure rework. Given an existing config with non-canonical Tiddly entries (`work_prompts` and `personal_prompts`, each with its own PAT), `configure` adds the canonical CLI-managed entries alongside them and names the preserved entries.

Set up the fixture:

1. Mint two PATs via `tiddly tokens create cli-mcp-test-t2-11-...`.
2. Write both as non-CLI-managed entries in `$CLAUDE_CODE_CONFIG` (pointing at `$TIDDLY_PROMPT_MCP_URL`). The `write_multi_entry_prompts` helper in `lib.sh` does this.
3. Run `bin/tiddly mcp configure claude-code`.

After:

- Exit 0.
- Stdout contains `Preserved non-CLI-managed entries in claude-code:` followed by both `work_prompts` and `personal_prompts` (order-independent).
- `jq`: `tiddly_prompts` added; `work_prompts` and `personal_prompts` survived.
- Stdout does **not** say `consolidate` / `Consolidation required` (that gate is gone).
- Remember to `unset` any plaintext PAT variables after the fixture write.

### T2.12 — Canonical update-in-place: no churn on re-run

Running `configure` twice in a row against an already-correctly-configured state must not churn tokens or rewrite the canonical entries. Under OAuth, existing PATs are validated and reused; under PAT auth, the login PAT is rewritten identically. Either way the bytes don't change.

1. Ensure a known-good state: `bin/tiddly mcp configure claude-code`.
2. Snapshot the canonical entries' JSON (hash `jq -c '.mcpServers.tiddly_notes_bookmarks'` and `.tiddly_prompts` separately).
3. Run `configure claude-code` again.
4. Re-hash. Both hashes must match exactly.

Stdout contains `Configured: claude-code`, no `unexpected URL` refusal.

The OAuth-vs-PAT outcome differs textually — under OAuth stdout says `Reused tokens:`; under PAT auth it does not (login PAT is used directly). Either path is correct. Worth recording in the report as a NOTE-line for log readability.

### T2.13 — `--force` overwrites a canonical entry at a non-Tiddly URL

A user hand-edited `tiddly_prompts` to point somewhere else (e.g. `https://example.com/my-prompts`). Default configure refuses; `--force` overwrites and logs the per-entry forcing line to **stderr**.

1. Seed a non-Tiddly URL on `.mcpServers.tiddly_prompts` via `jq`.
2. Run `configure claude-code`. Expected: non-zero exit; **stderr** contains `1 CLI-managed entry` (singular) + `has an unexpected URL` + `tiddly_prompts → https://example.com/my-prompts` + `re-run with --force`. (The mismatch error is a `RunE` return; cobra is configured with `SilenceErrors: true`, so `main.go` prints it to `os.Stderr` — none of it lands on stdout. Capture with e.g. `2>/tmp/stderr_refuse`.) **Before** the next command, snapshot the on-disk URL — it must still be the bad one (default refusal must not write). Do the snapshot in-band; asserting against the live file post-`--force` is meaningless because `--force` overwrites it.
3. Run `configure claude-code --force`, routing stderr separately (e.g. `... 2>/tmp/stderr_force`). Expected: exit 0; **stderr** (not stdout) contains `Forcing overwrite of tiddly_prompts (currently https://example.com/my-prompts)`; stdout contains `Configured: claude-code`; the live file's `tiddly_prompts.url` is now `$TIDDLY_PROMPT_MCP_URL`.

After, restore a clean state for subsequent phases: `mcp remove claude-code --delete-tokens; mcp configure claude-code`. Use `--delete-tokens` on the remove so the previous run's PATs are revoked before fresh ones are minted — otherwise every restore-clean-state incantation across T2.13 / T3.7 / T3.8 leaks two live tokens server-side, which accumulates across the run and can hit the tier token cap.

---

# Phase 3: Dry-run

No config writes; no server mutations.

### T3.1 — Dry-run, claude-code, user scope

`bin/tiddly mcp configure claude-code --dry-run` exits 0. Its output contains the banner `--- claude-code ---`, a `File:` line, and either `Before:` + `After:` sections or a `(new file)` marker. Both `tiddly_notes_bookmarks` and `tiddly_prompts` appear in the diff.

The SHA of `$CLAUDE_CODE_CONFIG` is unchanged before vs. after the command. The token count from `tokens list` is unchanged.

**Under PAT auth** (not OAuth), stderr contains `Using your current token for MCP servers`. Under OAuth, this advisory is absent.

**Tip:** the dry-run diff can dump a large real `~/.claude.json` (often 100 KB+). Redirect stdout to a file rather than capturing into a shell variable and echoing — `$(cmd)`-then-`echo` on large blobs is shell- flaky across zsh/bash.

### T3.2 — Dry-run, directory scope

`$TIDDLY_BIN mcp configure claude-code --scope directory --dry-run` (run from `$TEST_PROJECT`) shows the diff under the project-path key. `$CLAUDE_CODE_CONFIG` unchanged.

### T3.3 — Dry-run placeholder for would-be tokens

After ensuring no existing PATs to reuse (`mcp remove claude-code --delete-tokens`, which covers the clean case), `mcp configure claude-code --dry-run` shows the placeholder in the `After:` section. The `tokens list` count is unchanged (no tokens actually minted).

**Grep target:** `new-token-would-be-created` (inner text only — no angle brackets in the pattern). The Go source defines the placeholder as the literal string `<new-token-would-be-created>`, but it surfaces inside a JSON-marshaled string value (the `Authorization` header). Go's `json.MarshalIndent` defaults to `SetEscapeHTML(true)`, which emits `<` as the 6-character unicode-escape sequence `\u003c` and `>` as `\u003e`. So the actual on-the-wire bytes in the `After:` block are e.g. `"Authorization": "Bearer \u003cnew-token-would-be-created\u003e"`. The product's own unit tests at `cli/internal/mcp/configure_test.go:270-271` assert on the inner text only for exactly this reason — a literal `<...>` substring grep won't match.

### T3.4 — Dry-run, Codex

`bin/tiddly mcp configure codex --dry-run` shows `--- codex ---` banner and TOML-format `Before:` / `After:`. `$CODEX_CONFIG` unchanged.

### T3.5 — Dry-run, Claude Desktop

Analogous: `--- claude-desktop ---` banner; `After:` section includes `npx` and `mcp-remote`. Config unchanged.

### T3.6 — Dry-run does NOT emit the real-run summary line

`bin/tiddly mcp configure claude-code --dry-run` output does not contain `Configured: claude-code` — the summary line is gated on non-dry-run. The banner and diff are the dry-run signal.

### T3.7 — Dry-run on a URL-mismatch warns but does not abort

**Setup:** re-seed the T2.13 fixture — T2.13 ends by restoring clean state, so the bad URL is gone at this point. `jq`-overwrite `.mcpServers.tiddly_prompts` to a non-Tiddly URL like `https://example.com/my-prompts` (a fresh canonical-shaped entry with `type: "http"`, the bad URL, and any well-formed `headers.Authorization: "Bearer bm_..."` value). Then:

- `mcp configure claude-code --dry-run` exits 0 (dry-run is tolerant of mismatches — a real run would fail-closed).
- **Stderr** (not stdout) contains `Warning: tiddly_prompts at https://example.com/my-prompts — real run will require --force`.
- **Stdout** contains the normal dry-run diff.
- `$CLAUDE_CODE_CONFIG` is unchanged.

### T3.8 — Dry-run + `--force` suppresses the warning, shows the overwrite

With the same non-Tiddly-URL state, `mcp configure claude-code --dry-run --force` exits 0.

- **Stderr** does NOT contain `real run will require --force` (warning suppressed under `--force`).
- **Stderr** does NOT contain `Forcing overwrite of` (that log is non-dry-run only).
- **Stdout** contains the canonical prompts URL so the user can see what the real-run overwrite would write.
- `$CLAUDE_CODE_CONFIG` unchanged.

After, restore a clean state for subsequent phases: `mcp remove claude-code --delete-tokens; mcp configure claude-code` (same `--delete-tokens` rationale as T2.13's restore).

---

# Phase 4: Status

### T4.1 — Status across tools (default path)

`bin/tiddly mcp status` exits 0 and renders a per-tool tree. For scopes with no Tiddly entries: the output contains `No Tiddly servers configured. Run '` followed by a hint like `tiddly mcp configure claude-code`. For scopes with Tiddly entries: server rows end with `(<config_key>)`. Header is `MCP Servers:`.

### T4.2 — Status with explicit `--path`

`bin/tiddly mcp status --path "$TEST_PROJECT"` has the header `MCP Servers (path: $TEST_PROJECT):`. The claude-code directory-scope section shows an annotation indicating that directory-scope entries are stored in the user-scope file (`~/.claude.json`) under a `projects` subsection keyed by the project path (i.e. it makes the user-scope-file-with-project-subkey storage model visible in the output).

<!-- T4.3 intentionally omitted — invalid-path handling for `status --path` is covered by T1.5's shared-validator check; duplicating it here would test the same code path twice. -->

### T4.4 — Multi-entry rendered as multiple rows (KAN-112 regression)

After setting up `work_prompts` and `personal_prompts` (as in T2.11), `bin/tiddly mcp status` renders **each as its own row** under the claude-code prompts section — not folded under one "prompts" node. Both rows have the `(work_prompts)` and `(personal_prompts)` suffixes visible. Neither row appears under an "Other servers" section.

**Tip:** `mcp status` prefixes tree rows with `│` (U+2502 box-drawing), which isn't POSIX whitespace. Anchor greps on the trailing `(<name>)` suffix, not on leading whitespace.

After, reconfigure and then sweep any accumulated `cli-mcp-test-*` PATs to stay under the tier token cap (see the inline sweep snippet at the end of [§ Phase 5](#phase-5-remove)).

---

# Phase 5: Remove

### T5.1 — Remove claude-code, user scope

`bin/tiddly mcp configure claude-code` then `bin/tiddly mcp remove claude-code`: exit 0, stdout contains `Removed tiddly_notes_bookmarks, tiddly_prompts from claude-code.` and a `Backed up previous config to <path>` line. The reported backup path exists and its SHA matches the pre-remove SHA. Both canonical entries are gone from the live config; other entries preserved. Stderr may contain an orphan-token warning.

### T5.2 — Remove claude-code, directory scope

Configure then remove `--scope directory` from within `$TEST_PROJECT`. The `.projects["$TEST_PROJECT"].mcpServers` object has no `tiddly_*` keys; top-level `.mcpServers` is unchanged.

### T5.3 — Remove Codex

Configure then remove `codex`. Stdout: `Removed tiddly_notes_bookmarks, tiddly_prompts from codex.` The TOML has no `tiddly_*` tables.

### T5.4 — Remove Claude Desktop

Configure then remove `claude-desktop`. Stdout: `Removed tiddly_notes_bookmarks, tiddly_prompts from claude-desktop.` Stderr contains `Restart Claude Desktop to apply changes.` (note: this flavor is bare, without the `Warning:` prefix that the configure path adds — this asymmetry is the actual product behavior; record as informational).

### T5.5 — Remove `--servers content` is partial

Configure claude-code, then `mcp remove claude-code --servers content`. `tiddly_notes_bookmarks` removed; `tiddly_prompts` still present.

### T5.6 — Remove `--servers prompts` is partial

Symmetric to T5.5.

### T5.7 — Remove `--delete-tokens` (clean single-entry case)

Clean install: `mcp remove claude-code` to clear, then `mcp configure claude-code` (note the `Created tokens: cli-mcp-...` names), then `mcp remove claude-code --delete-tokens`. Stdout contains `Deleted tokens:` listing those same names. `tokens list` confirms they are gone server-side.

### T5.8 — Remove `--delete-tokens` preserves non-CLI-managed entries and their PATs (headline)

The canonical-name-only remove contract: revoking CLI-managed tokens must not touch user-managed entries or their PATs.

Fixture setup:

1. Mint four PATs with clearly scoped names: `cli-mcp-test-t5-8-content-*`, `-prompts-*`, `-work-*`, `-personal-*`.
2. Fresh `mcp remove claude-code`.
3. Write `work_prompts` / `personal_prompts` via `write_multi_entry_prompts` (with the work + personal PATs).
4. Write **full** canonical entries into `$CLAUDE_CODE_CONFIG` via `jq` — not just header overwrites. The revoke path in `mcp remove` only extracts a PAT for revocation if the entry's URL classifies as a Tiddly MCP URL (see `cli/internal/mcp/claude_code.go`'s `isTiddlyContentURL` / `isTiddlyPromptURL`). So each canonical entry must include `type: "http"`, the correct Tiddly URL, **and** the PAT in `headers.Authorization`:
   - `tiddly_notes_bookmarks` → `url: $TIDDLY_CONTENT_MCP_URL`, `Authorization: "Bearer $PAT_CONTENT_58"`.
   - `tiddly_prompts`         → `url: $TIDDLY_PROMPT_MCP_URL`, `Authorization: "Bearer $PAT_PROMPTS_58"`.
   Wrong URL here means the revoke path never sees the PAT, the assertion false-fails, and you'll misclassify a correct product as a bug.
5. Record which of the four test-token IDs exist.
6. Run `mcp remove claude-code --delete-tokens`.

After:

- Exit 0. Stdout contains `Removed tiddly_notes_bookmarks, tiddly_prompts from claude-code.` and `Deleted tokens:` listing **exactly** the content + prompts test tokens (not work / personal).
- Server-side: the content + prompts PATs are gone from `tokens list`; work + personal PATs remain.
- Live config: `work_prompts` and `personal_prompts` entries still present; `tiddly_*` entries gone.

### T5.8b — Shared-PAT consolidated warning

Scenario: a canonical entry being revoked shares its PAT with one or more retained (non-CLI-managed) entries. The warning fires as **one consolidated line per revoking entry**, listing every retained entry that shares its PAT, sorted alphabetically.

Fixture shape:

- `tiddly_notes_bookmarks` with its own distinct PAT (must NOT appear in the warning).
- `tiddly_prompts`, `work_prompts`, `personal_prompts` all sharing a single PAT.

Concrete recipe (one way to build this — adapt if your shell differs):

```bash
bin/tiddly mcp remove claude-code --delete-tokens 2>/dev/null || true
uniq=$(openssl rand -hex 3)
PAT_CONTENT=$(bin/tiddly tokens create "cli-mcp-test-shared-content-$uniq" 2>&1 | awk '/^  bm_/ {print $1}')
PAT_SHARED=$(bin/tiddly tokens create  "cli-mcp-test-shared-$uniq"         2>&1 | awk '/^  bm_/ {print $1}')
[ -n "$PAT_CONTENT" ] && [ -n "$PAT_SHARED" ] || { echo "FATAL: T5.8b token mint failed"; exit 1; }

[ -f "$CLAUDE_CODE_CONFIG" ] || echo "{}" > "$CLAUDE_CODE_CONFIG"
jq --arg curl "$TIDDLY_CONTENT_MCP_URL" --arg purl "$TIDDLY_PROMPT_MCP_URL" \
   --arg content "$PAT_CONTENT" --arg shared "$PAT_SHARED" \
   '.mcpServers = (.mcpServers // {})
    | .mcpServers.tiddly_notes_bookmarks = {type:"http", url:$curl, headers:{Authorization:("Bearer "+$content)}}
    | .mcpServers.tiddly_prompts         = {type:"http", url:$purl, headers:{Authorization:("Bearer "+$shared)}}
    | .mcpServers.work_prompts           = {type:"http", url:$purl, headers:{Authorization:("Bearer "+$shared)}}
    | .mcpServers.personal_prompts       = {type:"http", url:$purl, headers:{Authorization:("Bearer "+$shared)}}' \
   "$CLAUDE_CODE_CONFIG" > "$CLAUDE_CODE_CONFIG.tmp" && mv "$CLAUDE_CODE_CONFIG.tmp" "$CLAUDE_CODE_CONFIG"
chmod 0600 "$CLAUDE_CODE_CONFIG"
unset PAT_CONTENT PAT_SHARED uniq      # consume immediately; no PAT lingers in the shell
```

Then run `mcp remove claude-code --servers prompts --delete-tokens`:

- Exit 0.
- **Stderr** contains exactly: `Warning: token from tiddly_prompts is also used by personal_prompts, work_prompts (still configured); revoking will break those bindings.` The retained names are comma-joined, alphabetically sorted (→ `personal_prompts` before `work_prompts`).
- **Stderr** does NOT name `tiddly_notes_bookmarks` (its PAT is not shared with the revoke target).
- Stdout contains `Deleted tokens:`.
- Canonical prompts entry removed; `work_prompts` / `personal_prompts` entries preserved (their PATs are now dead, but the entries themselves are still in the config).

**Note:** this test intentionally leaves `work_prompts` and `personal_prompts` with a revoked PAT. T5.9 explicitly wipes those residuals before running (see the reset step just below T5.8d).

### T5.8c — `--delete-tokens` note when PAT doesn't match any CLI-minted token

Scenario: the canonical `tiddly_prompts` entry holds a PAT that was created via `tokens create` but with a name that **doesn't** match the `cli-mcp-*` pattern (e.g. `manual-test-pat-<hex>`). The CLI cannot revoke it (by name-prefix matching), but it must surface a per-entry explanation.

Fixture: fresh configure, then `jq`-overwrite `tiddly_prompts`'s Authorization with the manually-named PAT. **Mint the manual token with a unique suffix** (e.g. `uniq=$(openssl rand -hex 3); bin/tiddly tokens create "manual-test-pat-$uniq"`) and record `$uniq` — you need it for precise cleanup at the end of the test.

Run `mcp remove claude-code --servers prompts --delete-tokens`:

- Exit 0.
- **Stdout** (outcome report, not warning) contains: `Note: no CLI-created token matched the token attached to tiddly_prompts; nothing was revoked. Manage tokens at https://tiddly.me/settings.`
- Stdout does NOT contain `Deleted tokens:`.

**Cleanup (required).** The manually-named token won't match Phase 9's `cli-mcp-*` diff-cleanup filter, so revoke it explicitly before moving on. Look it up by **exact name equality** — not a prefix match — to avoid grabbing a leaked `manual-test-pat-*` token from a prior aborted run:

```bash
manual_id=$(bin/tiddly tokens list 2>/dev/null | awk -v nm="manual-test-pat-$uniq" '$2 == nm {print $1; exit}')
[ -n "$manual_id" ] && bin/tiddly tokens delete "$manual_id" --force
```

### T5.8d — Orphan-warning filter excludes tokens still referenced by retained entries

Scenario: after `configure`, copy the `tiddly_prompts` PAT into a new `work_prompts` entry so the CLI-minted PAT is still in active use. Then run `mcp remove claude-code` **without** `--delete-tokens`. The orphan-warning path fires, but the still-in-use PAT must NOT appear in the warning.

**Recommended fixture idiom** — in-place `jq` rewrite that copies the prompts PAT to `work_prompts` without ever landing the plaintext in a shell variable:

```bash
bin/tiddly mcp configure claude-code >/dev/null
jq '.mcpServers.work_prompts = {
      type: "http",
      url: env.TIDDLY_PROMPT_MCP_URL,
      headers: .mcpServers.tiddly_prompts.headers
    }' "$CLAUDE_CODE_CONFIG" > "$CLAUDE_CODE_CONFIG.tmp" && mv "$CLAUDE_CODE_CONFIG.tmp" "$CLAUDE_CODE_CONFIG"
chmod 0600 "$CLAUDE_CODE_CONFIG"
# No captured token — no `echo`/`set -x` leak surface.
```

Then run `mcp remove claude-code` (no `--delete-tokens`) and assert:

- **Stderr** does NOT contain a `Warning: PATs created for claude-code may still exist:` line that names the prompts token (either no warning at all, or a warning that covers only the content token).
- `tokens list` still shows the prompts token.
- `work_prompts` entry survives the remove.

**Reset before T5.9.** T5.8b left `work_prompts` and `personal_prompts` in the config (with a revoked PAT); T5.8d overwrites `work_prompts` and leaves `personal_prompts` alone. `configure`/`remove` are canonical-only and will not clear those — so explicitly wipe them now so T5.9 runs against a true clean slate:

```bash
jq 'del(.mcpServers.work_prompts, .mcpServers.personal_prompts)' "$CLAUDE_CODE_CONFIG" > "$CLAUDE_CODE_CONFIG.tmp" && mv "$CLAUDE_CODE_CONFIG.tmp" "$CLAUDE_CODE_CONFIG"
```

This is on-disk only — server-side PAT cleanup (for the CLI-minted token now orphaned in `tokens list` after T5.8d's removal) is deferred to Phase 8/9's diff-based sweep, which handles it by design.

### T5.9 — Remove without `--delete-tokens` — orphan warning

Configure, then remove (no `--delete-tokens`).

- **Stderr** contains `Warning: PATs created for claude-code may still exist:` followed by `cli-mcp-*` names (don't assert on exact names — environment-dependent).
- **Stderr** contains `Run 'tiddly mcp remove claude-code --delete-tokens' to revoke` (the tool name is interpolated, not a `<tool>` placeholder).

### T5.10 — Remove idempotent — no-op path

After T5.9, re-running `mcp remove claude-code` exits 0. Stdout contains `No CLI-managed entries found in claude-code.` Stdout does NOT contain `Removed tiddly_notes_bookmarks` (the CLI distinguishes "removed something" from "nothing to remove" and must not lie).

### End-of-phase housekeeping

Sweep accumulated `cli-mcp-test-*` tokens so later phases don't blow the tier token cap. These test-only PATs are named with a reserved `cli-mcp-test-` prefix; sweep them specifically, never the `cli-mcp-<tool>-<server>-*` names (those are minted by `configure` and may still be referenced by live configs). One pass with `tokens list` filtered on `cli-mcp-test-` + `tokens delete <id> --force` is enough. Verify `bin/tiddly auth status` still shows `oauth` before proceeding.

---

# Phase 6: Skills

No structural changes in this round; included for completeness.

### T6.1 — Skills configure, claude-code, user scope

`bin/tiddly skills configure claude-code` exits 0. The CLI prints `cfgResult.DestPath` verbatim (`cli/cmd/skills.go`) and the resolver returns an **absolute** path for user scope (`$HOME/.claude/skills`, no tilde). So output is either `claude-code: Configured N skill(s) to <absolute-home>/.claude/skills` (e.g. `/Users/you/.claude/skills`) or `claude-code: No skills to configure.` — both valid depending on how many prompts are tagged. Files land at `$CLAUDE_SKILLS_DIR` on disk.

### T6.2 — Claude-code, directory scope

In `$TEST_PROJECT`: `$TIDDLY_BIN skills configure claude-code --scope directory`. For directory scope the resolver returns the **relative** path `.claude/skills` — so the output reads `claude-code: Configured N skill(s) to .claude/skills` (no tilde, no `$TEST_PROJECT` prefix). Files land at `$TEST_PROJECT/.claude/skills/` because that's the cwd the relative path resolves against.

### T6.3 — Codex, user scope

`bin/tiddly skills configure codex` exits 0. Output either `codex: Configured N skill(s) to <absolute-home>/.agents/skills` (absolute path, no tilde) or `codex: No skills to configure.`

### T6.4 — Codex, directory scope

`$TIDDLY_BIN skills configure codex --scope directory` from `$TEST_PROJECT`: output contains the relative `.agents/skills` (no `$TEST_PROJECT` prefix in the text). Files extracted to `$TEST_PROJECT/.agents/skills/` on disk.

### T6.5 — Claude Desktop, user scope (zip export)

`bin/tiddly skills configure claude-desktop` exits 0. If skills exist, output mentions a zip path ending in `tiddly-skills-*.zip` plus the hint `Upload this file to Claude Desktop via Settings > Skills.` The zip lands in `os.TempDir()` — on macOS that's `$TMPDIR` (usually under `/var/folders/.../T/`), not `/tmp`. Don't pin the `/tmp` prefix; match on the filename pattern.

### T6.6 — `--tags` filter, default `match=all`

`skills configure claude-code --tags python,skill` installs exactly the set of prompts whose tags include **both** `python` AND `skill`.

**Before running,** wipe the skills dir: `rm -rf "$CLAUDE_SKILLS_DIR"`. Phase 0's sanitize cleared it at session start, but T6.1 has since installed skills (which `skills configure` doesn't remove on re-run; see `cli/cmd/skills.go:52`). A stale directory poisons the equality compare.

**Verify with exact set equality** — compute the expected set client-side by replaying the backend's filter + normalize logic:

1. `bin/tiddly export --types prompt` gives full prompt metadata (including tag lists).
2. Filter to prompts whose tags contain both `python` and `skill`.
3. Truncate each matching `.name` to the client's `name_max` (64 for claude-code). Mirror's the backend's `prompt.name[:64]` in `backend/src/services/skill_converter.py`.
4. Collect into a **set** (e.g. `jq ... | sort -u`) — set semantics mean that if two prompts collide at the truncated name, they collapse to one entry, matching the backend's `_build_skills_dict` last-one-wins dedup (since we only care about membership here, we don't need to replay "which content won").

Then compare the expected set against `ls -1 "$CLAUDE_SKILLS_DIR" | sort -u`. The two must be **equal**, not just subset-related, and non-empty (otherwise an all-empty compare false-passes).

One way to do this (adapt if `jq` / field shape differs in your environment):

```bash
rm -rf "$CLAUDE_SKILLS_DIR"
bin/tiddly skills configure claude-code --tags python,skill >/dev/null 2>&1
export_json=$(mktemp)
bin/tiddly export --types prompt > "$export_json" 2>/dev/null
expected=$(jq -r '
    .prompts // []
    | map(select((.tags // []) as $t | ($t | index("python")) and ($t | index("skill"))))
    | map(.name[0:64])
    | unique
    | .[]
' "$export_json" | LC_ALL=C sort)
rm -f "$export_json"
installed=$(ls -1 "$CLAUDE_SKILLS_DIR" 2>/dev/null | LC_ALL=C sort)
# Assertions:
#   - $expected and $installed are non-empty (otherwise SKIP)
#   - $expected == $installed (exact set equality)
```

If `$expected` is empty, SKIP with "no prompts in dev DB match both python+skill tags."

**Note:** `jq`'s string slicing is codepoint-based, matching the backend's Python `name[:64]` slicing — so membership equality holds regardless of whether prompt names contain multibyte characters. (Earlier revisions of this doc warned of a byte-vs-codepoint mismatch; that was wrong — `jq -n '"😀abc"|.[0:1]'` returns `"😀"` intact.)

Snapshot the T6.6 `$installed` into `t76_installed` for T6.7's superset check.

### T6.7 — `--tag-match any`

`--tag-match any` installs prompts matching **at least one** of the tags. Same structure as T6.6, with two changes:

1. Filter predicate uses OR instead of AND: `($t | index("python")) or ($t | index("skill"))`.
2. Wipe the dir first (same rationale as T6.6): `rm -rf "$CLAUDE_SKILLS_DIR"`.

Assert exact set equality between the normalized expected set and `$installed`, same as T6.6. Additionally assert T6.7's `$installed` is a **superset** of T6.6's: `comm -23 <(echo "$t76_installed") <(echo "$installed")` is empty (every T6.6 name appears in T6.7).

### T6.8 — Auto-detect

`bin/tiddly skills configure` exits 0, one output line per detected tool.

### T6.9 — Invalid scope

`skills configure --scope invalid` exits non-zero; error contains `invalid scope "invalid". Valid scopes: user, directory`.

### T6.10 — Skills list

`bin/tiddly skills list` exits 0. Output starts with `Available skills (N prompts):` or `No prompts found.`

### T6.11 — Skills list with tag filter

`bin/tiddly skills list --tags python` exits 0, lists only `python`-tagged prompts.

---

# Phase 7: Error handling

Pure validation-failure cases; no side effects on configs or tokens.

| Test | Command | Expected |
|---|---|---|
| T7.1 | `mcp configure invalid-tool` | non-zero; `unknown tool "invalid-tool". Valid tools: claude-desktop, claude-code, codex` |
| T7.2 | `mcp remove invalid-tool` | non-zero; same error text |
| T7.3 | `mcp configure claude-code --scope bad-scope` | non-zero; `invalid scope "bad-scope". Valid scopes: user, directory` |
| T7.4 | `mcp configure claude-code --scope local` | non-zero; `invalid scope "local". Valid scopes: user, directory` |
| T7.5 | `mcp configure claude-code --scope project` | non-zero; `invalid scope "project". Valid scopes: user, directory` |
| T7.6 | `mcp configure claude-code --servers invalid` | non-zero; `invalid server "invalid" in --servers flag. Valid values: content, prompts` |
| T7.7 | `mcp configure claude-code --servers ""` | non-zero; `--servers flag requires at least one value: content, prompts` |
| T7.8 | `mcp configure claude-desktop` when Claude Desktop is NOT detected (skip otherwise) | non-zero; `claude-desktop is not installed on this system` |
| T7.9 | `skills configure claude-desktop --scope directory` | non-zero; `--scope directory is not supported by: claude-desktop` |
| T7.10 | `login --token "invalid_no_prefix"` | non-zero; `invalid token format: must start with 'bm_'` |
| T7.11 | `login --token "bm_definitely_not_valid_token"` | non-zero; `token verification failed` |

After these, verify `auth status` still shows `oauth` — two failed login attempts shouldn't have mutated credentials.

---

# Phase 8: Auth / logout

Runs at the end because subsequent phases need auth.

### T8.0 — Cleanup before logout

Before logging out, do the full diff-based cleanup (Phase 9 needs auth alive too, but this test establishes the invariant that no new `cli-mcp-*` token is minted between T8.0 and re-login at T8.3). Diff the current `cli-mcp-*` IDs against `$BACKUP_DIR/cli-mcp-ids-before.txt` and `tokens delete <id> --force` each addition.

Phase 9 re-runs this same cleanup as a safety net (belt-and-suspenders). If the no-new-tokens invariant held between T8.0 and T8.3, Phase 9 revokes zero additional tokens; if anything leaked, Phase 9 catches it.

### T8.1 — `mcp status` works without auth

`bin/tiddly logout`: exit 0, stdout `Logged out successfully.` `bin/tiddly mcp status`: exit 0, MCP tree still renders (read-only command; reads local config only).

### T8.2 — Destructive commands fail when logged out

Each of the following exits non-zero with an error containing `not logged in. Run 'tiddly login' to authenticate`:

- `bin/tiddly mcp configure claude-code`
- `bin/tiddly skills list`
- `bin/tiddly skills configure claude-code`

### T8.3 — Re-login

**Engineer step (manual — device flow):**

```bash
bin/tiddly login
```

**Agent:** `bin/tiddly auth status` → shows `Auth method: oauth` with dev account.

---

# Phase 9: Teardown

Explicit — run this as the last Bash call of the session. The block below is a reference implementation; the behavioral goals are:

- Revoke every `cli-mcp-*` token that appeared during this run (diff against the Phase 0 snapshot; revoke only the additions). Fail-closed — if auth is dead or a token delete fails, stop and preserve `$BACKUP_DIR` so the engineer can finish manually.
- Restore the real config files and skills directories from `$BACKUP_DIR`.
- Sweep CLI-emitted sibling backups (`<config>.bak.*`) that appeared during this run (delta against Phase 0's `siblings-before.txt` snapshot — never destroy pre-existing backups).
- Copy `$REPORT` to a retained location (e.g. `<repo-root>/test-run-<UTC-ts>.md`) **before** deleting `$BACKUP_DIR`.
- Delete `$TEST_PROJECT` and `$BACKUP_DIR` only if every previous step succeeded.

Adapt the bash below as needed. If any step fails, print recovery instructions (at minimum: the `cp -p <backup> <live>` commands the engineer would need to restore manually) and leave `$BACKUP_DIR` on disk.

```bash
set -euo pipefail
source cli/tests_agentic/lib.sh
# Re-export paths from Phase 0 (adjust to your session's actual values):
export BACKUP_DIR=<from Phase 0>
export TEST_PROJECT=<from Phase 0>
export REPORT=$BACKUP_DIR/test-report.md
export TIDDLY_BIN=$PWD/bin/tiddly
export CLAUDE_CODE_CONFIG=$HOME/.claude.json
export CLAUDE_DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"  # macOS
export CODEX_CONFIG=$HOME/.codex/config.toml
export CLAUDE_SKILLS_DIR=$HOME/.claude/skills
export CODEX_SKILLS_DIR=$HOME/.agents/skills

errors=0
note() { echo "  $*"; }
bail_on_errors() {
    if [ "$errors" -gt 0 ]; then
        echo
        echo "FATAL: teardown hit $errors error(s). Preserving \$BACKUP_DIR."
        echo "       Originals are at:"
        [ -f "$BACKUP_DIR/.claude.json" ]                && echo "         cp -p '$BACKUP_DIR/.claude.json' '$CLAUDE_CODE_CONFIG'"
        [ -f "$BACKUP_DIR/claude_desktop_config.json" ]  && echo "         cp -p '$BACKUP_DIR/claude_desktop_config.json' '$CLAUDE_DESKTOP_CONFIG'"
        [ -f "$BACKUP_DIR/config.toml" ]                 && echo "         cp -p '$BACKUP_DIR/config.toml' '$CODEX_CONFIG'"
        echo "       When done: rm -rf '$BACKUP_DIR' '$TEST_PROJECT'"
        exit 1
    fi
}

# ---- Step 1: revoke this-run's cli-mcp-* tokens ---------------------------
# Diff current tokens against the Phase 0 snapshot; revoke only additions.
# Requires OAuth alive. If auth is dead, report the list of new names for
# manual web-UI revocation and bail — do NOT delete $BACKUP_DIR in that case.
auth_mode=$("$TIDDLY_BIN" auth status 2>&1 | awk -F': ' '/^Auth method/ {print $2; exit}' | tr -d '[:space:]')
if [ "$auth_mode" != "oauth" ]; then
    echo "WARNING: auth mode is '$auth_mode', not oauth — cannot run diff-based token cleanup."
    echo "         New cli-mcp-* tokens from this run will orphan server-side."
    echo "         Re-authenticate, then manually compare:"
    echo "           diff <(bin/tiddly tokens list | awk '/cli-mcp-/ {print \$1}' | sort) \\"
    echo "                '$BACKUP_DIR/cli-mcp-ids-before.txt'"
    errors=$((errors+1))
else
    current=$("$TIDDLY_BIN" tokens list 2>/dev/null | awk '/cli-mcp-/ {print $1}' | LC_ALL=C sort)
    new_ids=$(comm -13 "$BACKUP_DIR/cli-mcp-ids-before.txt" <(echo "$current"))
    if [ -n "$new_ids" ]; then
        while read -r id; do
            [ -n "$id" ] || continue
            if "$TIDDLY_BIN" tokens delete "$id" --force >/dev/null 2>&1; then
                note "revoked token $id"
            else
                note "FAILED to revoke token $id"
                errors=$((errors+1))
            fi
        done <<< "$new_ids"
    else
        note "no new cli-mcp-* tokens to revoke"
    fi
fi

# ---- Step 2: restore real configs + skills dirs ---------------------------
restore() {
    local src="$1" dest="$2"
    if [ -e "$src" ]; then
        cp -p "$src" "$dest" && note "restored $dest" || { echo "WARN: could not restore $dest"; errors=$((errors+1)); }
    else
        rm -f "$dest" 2>/dev/null && note "removed $dest (no original)"
    fi
}
restore "$BACKUP_DIR/claude_desktop_config.json" "$CLAUDE_DESKTOP_CONFIG"
restore "$BACKUP_DIR/.claude.json"               "$CLAUDE_CODE_CONFIG"
restore "$BACKUP_DIR/config.toml"                "$CODEX_CONFIG"

restore_dir() {
    local src="$1" dest="$2"
    if [ -d "$src" ]; then
        rm -rf "$dest" && cp -rp "$src" "$dest" && note "restored $dest" || { echo "WARN: could not restore $dest"; errors=$((errors+1)); }
    else
        rm -rf "$dest" 2>/dev/null && note "removed $dest (no original)"
    fi
}
restore_dir "$BACKUP_DIR/claude-skills" "$CLAUDE_SKILLS_DIR"
restore_dir "$BACKUP_DIR/codex-skills"  "$CODEX_SKILLS_DIR"

# ---- Step 3: sweep CLI-emitted sibling backups (this-run only) ------------
# Every configure/remove wrote <config>.bak.<timestamp> siblings. Those hold
# copies of the sanitized test-state configs + their PATs; remove them.
# ONLY sweep siblings that appeared during THIS run — compute the delta
# against Phase 0's $BACKUP_DIR/siblings-before.txt so we don't silently
# destroy the user's older .bak.* files from prior CLI runs.
current_siblings=$(
    for cfg in "$CLAUDE_DESKTOP_CONFIG" "$CLAUDE_CODE_CONFIG" "$CODEX_CONFIG"; do
        find "$(dirname "$cfg")" -maxdepth 1 -name "$(basename "$cfg").bak.*" -type f 2>/dev/null
    done | LC_ALL=C sort
)
new_siblings=$(comm -13 "$BACKUP_DIR/siblings-before.txt" <(echo "$current_siblings"))
swept=0
while IFS= read -r bak; do
    [ -n "$bak" ] || continue
    rm -f "$bak" && swept=$((swept + 1))
done <<< "$new_siblings"
note "swept $swept sibling backup(s) created during this run"

# ---- Step 4: copy report to a retained location ---------------------------
retained="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/test-run-$(date -u +%Y%m%dT%H%M%SZ).md"
cp -p "$REPORT" "$retained" && note "report copied to $retained" || { echo "WARN: report copy failed"; errors=$((errors+1)); }

bail_on_errors

# ---- Step 5: delete sandbox -----------------------------------------------
rm -rf "$TEST_PROJECT" "$BACKUP_DIR"
echo
echo "Teardown complete. Report: $retained"
```

---

# User verification checklist (manual, not automatable)

- Claude Desktop actually connects to MCP servers after configure.
- MCP tools return real data.
- Prompts render through the prompt MCP server.
- Skills are invocable in Claude Code / Codex.
- OAuth device flow works end-to-end (`tiddly login` without `--token`).
- Uploaded skills zip works in Claude Desktop (Settings > Skills).

---

# Reference: known assumptions

Things the procedure quietly relies on. If any of these changes, the run's bookkeeping quietly goes wrong — worth re-reviewing if you touch the surfaces below.

- **`bin/tiddly tokens list` returns all tokens in one response.** No pagination parameter is passed; Phase 0's `cli-mcp-*` snapshot and Phase 9's diff-cleanup both assume the full set is visible in a single call. If `tokens list` ever paginates, both phases need an update to page through.
- **Peak run token count is ~15–25 `cli-mcp-*` tokens.** `cli-mcp-test-*` PATs are swept at the ends of Phases 4 and 5; `cli-mcp-<tool>-<server>-*` PATs minted by `configure` persist until Phase 8's pre-logout cleanup. If your test account's tier cap is tighter than ~30, raise it or use a dedicated test account.
- **The `--delete-tokens` restore idiom in T2.13 and T3.8 is safe because Phase 0 enforces OAuth.** Under PAT auth, revoking the canonical-slot PAT could revoke the session itself; Phase 0's preflight makes that inapplicable here.

---

# Reference: config shapes (one-liner each)

All tests assert via `jq -e` (JSON) or `uv run python3 -c 'import tomllib'` (TOML) with exit-code-only checks — never by printing values.

- **Claude Desktop** (JSON): `.mcpServers.<name> = {command:"npx", args:["mcp-remote", URL, "--header", "Authorization: Bearer bm_..."]}`
- **Claude Code, user scope** (JSON, `~/.claude.json`): `.mcpServers.<name> = {type:"http", url:URL, headers:{Authorization:"Bearer bm_..."}}`
- **Claude Code, directory scope** (same file): same shape under `.projects["<path>"].mcpServers.<name>`
- **Codex** (TOML, `~/.codex/config.toml` or `.codex/config.toml`): `[mcp_servers.<name>]` with `url` + `[mcp_servers.<name>.http_headers]` with `Authorization`

# Reference: backup filename format

Every destructive `configure`/`remove` writes a sibling:

```
<config_path>.bak.<YYYYMMDDTHHMMSSZ>        # first backup this UTC second
<config_path>.bak.<YYYYMMDDTHHMMSSZ>.1      # collision suffix (.1..1000)
```

Permissions match the source (0600 for files holding PATs). Never overwritten (O_EXCL). Phase 9's teardown sweeps them.

# Reference: key constants

| Constant | Value |
|---|---|
| Content server name | `tiddly_notes_bookmarks` |
| Prompts server name | `tiddly_prompts` |
| Content MCP URL (local) | `http://localhost:8001/mcp` |
| Prompts MCP URL (local) | `http://localhost:8002/mcp` |
| API URL (local) | `http://localhost:8000` |
| Token name pattern (CLI-minted) | `cli-mcp-<tool>-<server>-<6hex>` |
| Test-harness token naming convention | `cli-mcp-test-*` (reserved for ad-hoc test PATs, safe to bulk-delete) |
| Token prefix | `bm_` |
| Dry-run placeholder | `<new-token-would-be-created>` |
| Backup timestamp format | `YYYYMMDDTHHMMSSZ` (UTC) |

# Reference: tool × scope support

| Tool | user | directory |
|---|:---:|:---:|
| claude-desktop | yes | no |
| claude-code | yes | yes |
| codex | yes | yes |

Legacy scope values `local` and `project` are rejected at validation.

# Reference: skills extraction paths

| Tool | user scope | directory scope |
|---|---|---|
| claude-code | `~/.claude/skills/` | `.claude/skills/` (relative to cwd) |
| codex | `~/.agents/skills/` | `.agents/skills/` (relative to cwd) |
| claude-desktop | zip at `<os.TempDir()>/tiddly-skills-*.zip` (macOS: `$TMPDIR`, Linux: usually `/tmp`) | not supported |
