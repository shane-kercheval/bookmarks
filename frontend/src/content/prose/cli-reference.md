---
route: /docs/cli/reference
title: Docs - CLI Reference
description: Tiddly CLI command reference — login, logout, auth status, status, credential storage, token resolution, tokens, export, config, and shell completions.
---

# CLI Reference

Authentication, tokens, export, configuration, and other CLI commands.

## tiddly ai-instructions

Prints Tiddly's CLI instructions for AI agents — the command an agent should run first. It fetches the latest hosted guidance (`https://tiddly.me/llms-cli-instructions.txt`) and prints it, so the instructions stay current without a CLI release.

```
tiddly ai-instructions
```

- **No login required** — it only fetches a public file, so an agent can call it before `tiddly login`.
- **Offline-safe** — on any fetch failure it prints a minimal fallback that points at the URL and still exits 0, so it never breaks a workflow.

## Authentication

### tiddly login

Authenticates with the Tiddly API and stores credentials locally.

#### OAuth Login (default)

Running `tiddly login` without flags starts an OAuth device code flow:

```
tiddly login
```

1. The CLI prints a URL and a one-time code for you to enter in your browser.
2. After you authorize in the browser, the CLI stores both the access token and refresh token.
3. The CLI verifies the token by calling the API and displays your account email.

#### PAT Login

To authenticate with a Personal Access Token (useful for CI/CD or headless environments):

```
tiddly login --token bm_your_token_here
```

1. The CLI validates the `bm_` prefix.
2. Verifies the token against the API.
3. Stores the PAT in the system keyring (or file fallback).

> [!tip]
> **Generate a PAT**
>
> Create a Personal Access Token in [Settings > Personal Access Tokens](/app/settings/tokens) on tiddly.me.

### tiddly logout

Removes all stored credentials (PAT, OAuth access token, and OAuth refresh token) from the keyring or file store:

```
tiddly logout
```

### tiddly auth status

Displays the current authentication method, API URL, and user email. Read-only — does not modify any files.

```
tiddly auth status
```

Shows the active auth type (`pat`, `oauth`, `flag`, or `env`) and calls the API to display your account information.

### tiddly status

Shows a full overview of your CLI setup. Read-only — no files are modified.

```
tiddly status
```

Displays:

- CLI version
- Authentication status and method
- API health and latency
- Content counts (bookmarks, notes, prompts — fetched in parallel)
- MCP server status for each detected AI tool across user and directory scopes
- Installed skills across all tools and scopes

Use `--path` to specify which directory to inspect for directory-scoped configurations. Defaults to the current working directory.

```
tiddly status --path /path/to/project
```

## Credential Storage

Credentials are stored in the system keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service) under the service name `tiddly-cli`.

### File Fallback

When the system keyring is unavailable, credentials are stored in `~/.config/tiddly/credentials` (mode 0600, owner-only read/write). You may see this warning:

```
Warning: System keyring unavailable. Credentials stored in plaintext at ~/.config/tiddly/credentials
```

This is common in VMs, containers, WSL, and SSH sessions where the keyring is not unlocked by a graphical login. It is safe to ignore — the file store uses restricted permissions. To suppress the warning, pass `--keyring=file` to explicitly choose file storage.

## Token Resolution

When a command needs a token, the CLI checks these sources in order:

| Priority | Source | Details |
| --- | --- | --- |
| 1 | `--token` flag | Explicit token passed on the command line |
| 2 | `TIDDLY_TOKEN` env var | Environment variable |
| 3 | Stored PAT | From keyring or file fallback |
| 4 | Stored OAuth JWT | Auto-refreshed if expired |

> [!info]
> Commands that require session-only endpoints (e.g., token management) swap steps 3 and 4, preferring the OAuth JWT over a stored PAT.

## Tokens

Manage Personal Access Tokens for programmatic API access. Requires OAuth login (browser-based).

```
tiddly tokens list                       # list all tokens
tiddly tokens create "My Token"          # create a new token
tiddly tokens create "CI" --expires 90   # create with 90-day expiration
tiddly tokens delete <id>                # delete (with confirmation)
tiddly tokens delete <id> --force        # delete without confirmation
```

## Export

Bulk export your content as JSON for backup or migration.

```
tiddly export                            # export all content as JSON
tiddly export --types bookmark,note      # export specific content types
tiddly export --output backup.json       # write to file
tiddly export --include-archived         # include archived items
```

## Config

View and modify CLI configuration. Settings can also be set via environment variables (`TIDDLY_API_URL`, `TIDDLY_UPDATE_CHECK`).

```
tiddly config list                       # show all config values
tiddly config get api_url                # get a specific value
tiddly config set api_url http://...     # set a value
tiddly config set update_check false     # disable auto-update checks
```

The CLI reads configuration from `~/.config/tiddly/config.yaml` (respects `$XDG_CONFIG_HOME`):

```
api_url: https://api.tiddly.me
update_check: true
```

Settings can be overridden at multiple levels. The CLI resolves values in this order (highest priority first):

| Priority | Source | Example |
| --- | --- | --- |
| 1 (highest) | CLI flags | `--api-url`, `--token` |
| 2 | Environment variables | `TIDDLY_API_URL`, `TIDDLY_UPDATE_CHECK` |
| 3 | Config file | `~/.config/tiddly/config.yaml` |
| 4 (lowest) | Defaults | `https://api.tiddly.me`, `true` |

## Shell Completions

Generate shell completion scripts for tab completion of commands and flags.

```
source <(tiddly completion bash)          # Bash (add to ~/.bashrc)
source <(tiddly completion zsh)           # Zsh (add to ~/.zshrc)
tiddly completion fish | source           # Fish
```
