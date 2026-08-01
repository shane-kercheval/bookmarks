---
route: /docs/api
title: Docs - API
description: Tiddly REST API overview — Personal Access Token authentication, bookmark/note/prompt/content/tag/history endpoints, shared capabilities, Swagger docs, and rate limits.
---

# API

Access your bookmarks, notes, and prompts programmatically. The REST API supports everything the web app does — create, read, update, search, tag, and manage version history for all content types.

## Authentication

All API requests require a Personal Access Token (PAT) passed as a Bearer token:

```
Authorization: Bearer bm_your_token_here
```

Create a token in [Settings → Personal Access Tokens](/app/settings/tokens). Tokens are shown only once when created, so store them securely. You can also create tokens via the [CLI](/docs/cli/reference).

> [!warning]
> Treat tokens like passwords. Never commit them to version control or expose them in client-side code.

## Request Headers

Beyond `Authorization`, one optional header is worth knowing about:

`X-Request-Source` — a free-form tag identifying your client (for example, your app's name). It is recorded on each item's version history so changes can be traced back to where they originated. It is **audit/telemetry only — not access control**, and has no effect on what a request is allowed to do.

- Free-form: send any short identifier. There is no allowlist.
- Keep it to **20 characters or fewer** — longer values are truncated.
- Lowercased server-side; leading/trailing whitespace is trimmed.
- Optional: if omitted, the source is recorded as `unknown`.

> [!note]
> The source is a **header**, not a body field — a `metadata.source` in the request body is ignored. Tiddly's own clients send values like `web`, `cli`, `chrome-extension`, `mcp-content`, `mcp-prompt`, and `ios`; a third-party integration should send its own identifier.

## Endpoints

The API is organized around content types, with shared capabilities across all of them:

### Bookmarks

CRUD operations, URL-based duplicate detection, and automatic metadata scraping when creating from a URL.

### Notes

CRUD operations for markdown notes with title, description, content, and tags.

### Prompts

CRUD operations for Jinja2 prompt templates, plus a render endpoint that substitutes argument values into the template.

### Content (Unified Search)

Search across all content types at once with full-text search, substring matching, tag filtering, and in-content search within a single item.

### Tags

List all tags with usage counts, rename tags globally, and delete tags across all content.

### History

View version history for any item, compare versions with diffs, and restore to a previous version.

## Shared Capabilities

- **Pagination** — all list endpoints support offset/limit pagination
- **Sorting** — sort by created date, updated date, title, or last used
- **Tag filtering** — filter by tags with AND/OR matching
- **Optimistic locking** — pass `If-Unmodified-Since` to detect concurrent edits
- **Archive & trash** — soft-delete and archive operations with recovery
- **Relationships** — link any item to any other item across content types

## Interactive Docs

The full API reference with request/response schemas and a "Try it out" feature is available via Swagger:

[Open API Docs](https://api.tiddly.me/docs)

> [!warning]
> **AI endpoints require an interactive session**
>
> The `/ai/*` endpoints (tag / metadata / relationship / argument suggestions, plus `/ai/health`, `/ai/models`, and `/ai/validate-key`) are session-only (Clerk-issued JWTs) — Personal Access Tokens receive a 403 response. This is intentional: AI features are not designed for programmatic automation. PATs still work on every other content endpoint (bookmarks, notes, prompts, tags, filters, history).

## Rate Limits

API requests are rate-limited per account. Current limits are shown in [Settings → General](/app/settings). Rate limit headers (`X-RateLimit-Remaining`) are included in every response.

> [!tip]
> **MCP Integration**
>
> If you want AI assistants to access your content, consider using the [MCP servers](/docs/ai) instead of the raw API — they handle authentication, pagination, and tool definitions automatically.
