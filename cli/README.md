# Tiddly CLI

Go CLI tool for managing Tiddly integrations — authentication, MCP server configuration, skills configuration, data export, and self-updating.

## Prerequisites

- [Go 1.21+](https://go.dev/dl/) — already installed in the dev VM
- [golangci-lint](https://golangci-lint.run/welcome/install/) — installed at `$(go env GOPATH)/bin/golangci-lint`. The Makefile uses the full path so no PATH changes needed. To install/upgrade: `go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@latest`
- [GoReleaser](https://goreleaser.com/) — needed for local snapshot builds and releases. To install: `go install github.com/goreleaser/goreleaser/v2@latest`

## Quick Start

```bash
# Build
make cli-build        # outputs bin/tiddly

# Run
./bin/tiddly --help
./bin/tiddly login
./bin/tiddly auth status

# Test & lint
make cli-test
make cli-lint
```

## Development

### Building

```bash
cd cli
go build -o ../bin/tiddly .
```

Or from the repo root:

```bash
make cli-build
```

### Testing

```bash
cd cli
go test ./... -v              # verbose
go test ./... -count=1        # no cache
go test ./internal/auth/...   # single package
go test ./... -run TestLogin  # single test pattern
```

### Linting

```bash
cd cli
golangci-lint run ./...
```

Lint config is in `cli/.golangci.yml`. We exclude `fmt.Fprint*` and `http.ResponseWriter.Write` from errcheck since these are standard CLI/HTTP patterns where error returns are intentionally ignored.

### Project Structure

```
cli/
  main.go                     # Entry point
  .goreleaser.yaml            # GoReleaser config for cross-platform builds
  install.sh                  # curl installer script
  cmd/                        # Cobra command definitions
    root.go                   # Global flags, dependency injection, auto-update check
    login.go                  # tiddly login (OAuth + PAT)
    logout.go                 # tiddly logout
    auth.go                   # tiddly auth status
    status.go                 # tiddly status (overview)
    mcp.go                    # tiddly mcp configure/status/remove
    skills.go                 # tiddly skills configure/list
    tokens.go                 # tiddly tokens list/create/delete
    export.go                 # tiddly export
    completion.go             # tiddly completion bash/zsh/fish
    config.go                 # tiddly config list/get/set
    update.go                 # tiddly update (self-update)
    update_check.go           # Background auto-update notification
  internal/
    api/                      # HTTP client
      client.go               # Auth headers, error handling, 429 retry (idempotent methods only)
      users.go                # GET /users/me, /health
      tokens.go               # POST/GET/DELETE /tokens/
      content.go              # GET /{content_type}/ (count, list, get by ID)
      prompts.go              # GET /prompts/ (list, export skills archive)
    auth/                     # Authentication
      pkce_flow.go            # OAuth authorization-code + PKCE flow (loopback redirect)
      keyring.go              # Credential storage (keyring + file fallback)
      token_manager.go        # Token resolution chain, refresh
    config/                   # Configuration
      config.go               # ~/.config/tiddly/config.yaml via Viper
      state.go                # ~/.config/tiddly/state.json (ephemeral state like last_update_check)
    update/                   # Self-update logic
      update.go               # GitHub release checking, download, checksum, binary replacement
    mcp/                      # MCP server management
      detect.go               # AI tool detection (PATH + config dirs)
      resolve.go              # Scope validation and config path resolution
      install.go              # Install orchestration, PAT creation, dry-run
      claude_desktop.go       # Claude Desktop config (JSON, uses npx mcp-remote)
      claude_code.go          # Claude Code config (JSON, direct HTTP entries)
      codex.go                # Codex config (TOML)
    skills/                   # Skills (prompt export)
      install.go             # Fetch prompts and write as SKILL.md files
    export/                   # Bulk export
      export.go               # Streaming JSON export
    testutil/                 # Shared test infrastructure
      mock_api.go             # httptest server builder
      mock_creds.go           # In-memory credential store
      mock_exec.go            # Mock ExecLooker for PATH detection
      cmd_helper.go           # In-process Cobra command runner
      fixtures.go             # Shared response fixtures
      archive.go              # tar.gz builder for update tests
```

### Test Patterns

Tests use dependency injection — no build tags, no real keyring or network calls in tests.

- **API tests** use `testutil.NewMockAPI(t)` to create a mock HTTP server
- **Command tests** use `testutil.ExecuteCmd(t, cmd, args...)` to run Cobra commands in-process
- **Credential tests** use `testutil.NewMockCredStore()` (in-memory)
- **Table-driven tests** are the standard pattern: one test function with a `[]struct` of cases

## Releases

### Making a new release

```bash
# 1. Merge your PR to main, then:
git checkout main
git pull

# 2. Verify
make cli-release-check

# 3. Tag and push (triggers the release pipeline)
git tag cli/v1.0.0
git push origin cli/v1.0.0

# 4. Monitor at: https://github.com/shane-kercheval/tiddly/actions
```

Pushing the tag triggers a GitHub Actions workflow (`.github/workflows/cli-release.yaml`) that builds and publishes everything automatically. No manual steps beyond tagging.

**Tag format:** `cli/v<semver>` (e.g., `cli/v1.0.0`, `cli/v1.1.0-rc.1`). The `cli/` prefix scopes the tag to the CLI so it doesn't look like the entire monorepo is versioned. This is the standard Go monorepo convention. Other parts of the repo (backend, frontend) deploy via Railway and don't use git tags.

**Pre-releases:** Tags like `cli/v1.0.0-rc.1` are valid. GoReleaser marks them as pre-releases on GitHub.

### How the release pipeline works

When you push a `cli/v*` tag, GitHub Actions runs [GoReleaser](https://goreleaser.com/), a tool that automates cross-compilation and release publishing:

1. GoReleaser reads `cli/.goreleaser.yaml` for build configuration
2. Strips the `cli/` tag prefix and uses the semver part (e.g., `1.0.0`) as the version
3. Cross-compiles the binary for 6 targets: linux/darwin/windows × amd64/arm64
4. Injects the version into the binary via `-ldflags "-X ...cmd.cliVersion=1.0.0"` (without this, `cliVersion` defaults to `"dev"` — see `cmd/status.go`)
5. Creates archives (`.tar.gz` for linux/mac, `.zip` for windows) and `checksums.txt` (SHA256)
6. Uploads everything as assets on a new **GitHub Release**

The release appears at `https://github.com/shane-kercheval/tiddly/releases` with downloadable binaries for each platform. There is no package registry — GitHub Releases is the distribution mechanism.

**Authentication:** The workflow uses `GITHUB_TOKEN`, which GitHub Actions provides automatically to every workflow run. No secrets to configure. The only prerequisite is that the repo allows Actions to create releases: Settings → Actions → General → Workflow permissions → **Read and write**.

### How users install and update

**New install:**
```bash
curl -fsSL https://raw.githubusercontent.com/shane-kercheval/tiddly/main/cli/install.sh | sh
```

The install script (`cli/install.sh`) detects OS/arch, downloads the matching archive from the latest GitHub Release, verifies the SHA256 checksum, and copies the binary to `/usr/local/bin` (or `~/.local/bin` if not writable). Users can override with `INSTALL_DIR=/custom/path`.

**Self-update:**
```bash
tiddly update
```

Calls the GitHub API for the latest release, compares versions using semver, downloads and verifies the archive, then atomically replaces the running binary via `os.Rename`. On permission errors, it suggests `sudo tiddly update`. Windows is not supported for self-update (returns an error with a download link).

**Auto-update notification:**

On every command (except `upgrade`, `completion`, `help`, `config`), the CLI starts a non-blocking background check for new versions. If the check completes before the command finishes, it prints a message to stderr. The check runs at most once per 24 hours (tracked in `~/.config/tiddly/state.json`). Users can disable with `tiddly config set update_check false` or `TIDDLY_NO_UPDATE_CHECK=1`.

### Local testing with GoReleaser

To test that cross-compilation works without publishing:

```bash
# Install goreleaser (one-time)
go install github.com/goreleaser/goreleaser/v2@latest

# Build snapshot (no tag required, no publish)
make cli-snapshot

# Binaries appear in cli/dist/
ls cli/dist/
```

### Version in local builds

`make cli-build` produces a binary with `cliVersion="dev"`. To inject a real version locally:

```bash
go build -ldflags "-X github.com/shane-kercheval/tiddly/cli/cmd.cliVersion=1.2.3" -o ../bin/tiddly .
```

### Key files

| File | Purpose |
|------|---------|
| `cli/.goreleaser.yaml` | Build matrix, archive format, checksum, monorepo tag prefix |
| `.github/workflows/cli-release.yaml` | Triggers on `cli/v*` tags, runs GoReleaser |
| `cli/install.sh` | POSIX shell installer for `curl \| sh` |
| `cli/internal/update/update.go` | GitHub API, checksum verification, atomic binary replace |
| `cli/cmd/update.go` | `tiddly update` command |
| `cli/cmd/update_check.go` | Background auto-update check |
| `cli/internal/config/state.go` | Persists `last_update_check` (separate from config.yaml) |

## User Documentation

For CLI usage, commands, and configuration, see the [CLI documentation](https://tiddly.me/docs/cli).

## Clerk OAuth Setup (Required for OAuth)

The `tiddly login` command (without `--token`) uses the OAuth authorization-code flow with PKCE and a loopback redirect (RFC 8252), against a Clerk **OAuth application**. This is separate from the web app's sign-in (which uses Clerk's frontend SDK directly).

### Clerk-side requirements (per instance)

On the Clerk instance (see `clerk/README.md` for what `clerk config pull` does and doesn't capture):

1. **Create an OAuth application** (e.g. "Tiddly CLI") — Dashboard → OAuth applications. Public client; redirect URI `http://127.0.0.1/callback` (port-less loopback — any ephemeral port matches). Note the **Client ID**.
2. **`pkce_required` ON** for the app (defaults OFF at creation — the same default-off flag class that bit M4; see the migration ledger).
3. **Instance flag `oauth_jwt_access_tokens` ON** — without it the token endpoint issues opaque tokens the backend can't verify (the observable symptom is a clean 401 plus a "not parseable as a JWT" warning log).
4. **`offline_access` scope** is requested by the CLI for refresh tokens; Clerk rotates them on every refresh — the CLI always stores whatever pair the token endpoint returns.

### Files to Update

The production defaults are hardcoded in **`cli/internal/auth/pkce_flow.go`** — `DefaultOAuthConfig()` (issuer `https://clerk.tiddly.me`, the production CLI OAuth app's client ID). These are public values by OAuth design — the client ID identifies the app, it authenticates nothing. For a fork, replace them with your instance's values; for local development against the dev instance, use the env overrides below instead of editing source.

### Local Development

For local development against the Clerk development instance:

- **PAT auth** (no OAuth needed): `tiddly login --token bm_xxx` validates against the API and stores the PAT
- **OAuth env overrides**: Point the CLI at a different Clerk instance without changing code (values live outside the repo — see the no-env-identifiers rule):
  ```bash
  TIDDLY_OAUTH_ISSUER=https://<dev-instance>.clerk.accounts.dev \
  TIDDLY_OAUTH_CLIENT_ID=<dev "Tiddly CLI" OAuth app client id> \
  tiddly login
  ```
