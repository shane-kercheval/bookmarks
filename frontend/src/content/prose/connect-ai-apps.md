---
route: /docs/ai
title: Docs - Connect AI Apps (OAuth)
description: Connect Claude, ChatGPT, Claude Code, and Codex to Tiddly's MCP servers with OAuth — paste a URL, sign in with your Tiddly account, done. Per-app steps, sync behavior, and troubleshooting.
---

# Connect AI Apps (OAuth)

Tiddly's MCP servers support OAuth sign-in. In any AI app that supports remote MCP connectors, you paste a server URL, sign in with your Tiddly account in the browser, approve access — and the app can use your content. No tokens to create or copy.

The two server URLs:

- **Bookmarks & notes:** `https://content-mcp.tiddly.me/mcp`
- **Prompts:** `https://prompts-mcp.tiddly.me/mcp`

Connect one or both — they're independent. This is the simplest path for every app listed below, including the terminal ones (Claude Code, Codex). The [CLI setup](/docs/cli/mcp) (`tiddly mcp configure`, token-based) remains fully supported for the cases OAuth can't cover: headless or remote machines (e.g. SSH, where no browser can open for sign-in), scripted setups, and tools without OAuth connector support (e.g. Antigravity). Existing CLI/token setups keep working unchanged.

<!-- widget:per-app-steps -->
<!-- Everything below this marker is also rendered inside the AI Integration
     setup widget's "Connect with OAuth" tab (AISetupWidget.tsx) — keep it
     self-contained: no H1, and nothing that assumes the intro above. -->

## Claude (web, desktop, and mobile)

1. Open **Settings → Connectors** in Claude (claude.ai or the desktop app) and choose **Add custom connector**.
2. Give it a name (e.g. "Tiddly Bookmarks & Notes"), paste a server URL, and add it.
3. A browser window opens — sign in with your Tiddly account and click **Allow**.
4. In a chat, enable the connector from the tools menu and ask Claude something like *"list my tiddly tags"* to confirm it's live.

Connectors are stored on your Claude **account**, not the device: add one on any surface and it appears on claude.ai, Claude Desktop, and the mobile apps automatically. Repeat with the second URL if you want prompts too — in Claude, your saved prompts also surface natively through the prompt picker.

## Claude Code (terminal)

```
claude mcp add --transport http -s user tiddly-content https://content-mcp.tiddly.me/mcp
claude mcp add --transport http -s user tiddly-prompts https://prompts-mcp.tiddly.me/mcp
```

Then start `claude`, run `/mcp`, and choose **Authenticate** for each server — a one-time browser sign-in per server; the authentication persists across projects.

`-s user` makes the servers available in every project. Omit it to configure only the current directory.

## Codex (terminal)

```
codex mcp add tiddly-content --url https://content-mcp.tiddly.me/mcp
codex mcp add tiddly-prompts --url https://prompts-mcp.tiddly.me/mcp
```

Codex detects OAuth support and opens the browser sign-in immediately. Configuration is global (`~/.codex/config.toml`); remove with `codex mcp remove <name>`.

> [!info]
> Codex reaches saved prompts through the prompt server's *tools* (it has no native prompt picker). To invoke prompts directly as `$skill-name`, also export them as [Skills](/docs/cli/skills).

## ChatGPT

As of August 2026 the path is: **Settings → Plugins → Add → Add MCP Server**. Name it, set the type to **Streamable HTTP**, paste a server URL, leave the bearer token blank, and Save. Then in **Plugins → MCPs**, open the server you just added and click **Authenticate** — sign in with your Tiddly account in the browser and approve. ChatGPT's settings layout changes frequently — look for wherever custom plugins/connectors/MCP apps are added if these labels have moved.

> [!info]
> ChatGPT's approval screen identifies it as **"Codex"** — the name OpenAI's agent stack registers for itself. That's expected; approve it if you initiated the connection.

## Troubleshooting

- **The sign-in window shows the app's own name** (e.g. "Claude", "MCP Inspector", "Codex" for ChatGPT) on the approval screen — that's the name the connecting app registered for itself. Approve only connections you initiated yourself.
- **Existing token-based setups are unaffected** — connecting via OAuth doesn't change or replace anything configured with `tiddly mcp configure`. Both can coexist (though two copies of the same server in one tool is confusing; [`tiddly mcp remove`](/docs/cli/mcp) cleans up the token-based one if you switch).
- **Sign-in fails with a scope or permission error on a connection that used to work** — clear/remove that connection in the app and connect fresh; the app is reusing a stale registration. Reconnecting registers it anew.
