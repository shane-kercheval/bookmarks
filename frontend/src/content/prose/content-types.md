---
route: /docs/features/content-types
title: Docs - Content Types
description: The three Tiddly content types — bookmarks, notes, and prompts — their fields, editor features, and the capabilities they share like tags, versioning, linking, and search.
---

# Content Types

Tiddly manages three content types — bookmarks, notes, and prompts — all organized with a shared tagging system and accessible from a unified interface.

## Bookmarks

Save URLs with automatically scraped metadata. When you add a URL, Tiddly fetches the page title, description, and full article content so your bookmarks are searchable.

- **URL** — the page address (automatically normalized)
- **Title** — auto-filled from the page, editable
- **Description** — short summary, auto-filled from meta tags
- **Content** — full page text extracted via article parser (also handles PDFs)
- **Tags** — for organizing and filtering

**Quick Add:** Copy a URL and press `{{shortcut:bookmark.pasteUrl}}` anywhere in the app (when not focused on an input) to instantly create a bookmark with scraped metadata. You can also click the **+** button or use the [browser extension](/docs/extensions).

**Interaction:** Clicking a bookmark's title opens the URL. Use the pencil icon to edit details. Hold `{{shortcut:bookmark.openLinkSilent}}` to open a link without updating the "last used" timestamp.

## Notes

Freeform markdown documents for capturing ideas, documentation, meeting notes, or anything else. Notes use a full-featured editor with formatting shortcuts and a rendered reading mode.

- **Title** — the note name
- **Description** — optional short summary
- **Content** — markdown body
- **Tags** — for organizing and filtering

### Editor Features

- **Slash commands** — type `/` at the start of a line for headings, lists, code blocks, links, and more
- **Command menu** — press `{{shortcut:editor.commandMenu}}` for a filterable palette of all formatting options
- **Reading mode** — toggle with `{{shortcut:editor.toggleReadingMode}}` to see rendered markdown preview
- **Callouts** — start a blockquote with `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, or `> [!CAUTION]` to render a colored callout; add your own title with `> [!NOTE] Custom title`
- **Display options** — toggle word wrap, line numbers, monospace font, and table of contents sidebar

See [Keyboard Shortcuts](/docs/features/shortcuts) for the full list of editor formatting shortcuts.

## Prompts

Jinja2 templates designed for AI assistants. Define reusable prompt templates with typed arguments that can be rendered with different values, shared via MCP, or exported as agent skills.

- **Name** — unique identifier (lowercase with hyphens, e.g. `code-review`)
- **Title** — human-readable display name
- **Description** — usage guide for the template
- **Content** — Jinja2 template body
- **Arguments** — typed parameters with names, descriptions, and required flags
- **Tags** — for organizing and filtering

See [Prompts & Templates](/docs/features/prompts) for full details on Jinja2 syntax, arguments, and rendering.

## Shared Features

All three content types share these capabilities:

- **Tags** — a global tag system shared across all content types. See [Tags & Filters](/docs/features/tags-filters).
- **Version history** — every edit is tracked with diffs and can be restored. See [Versioning](/docs/features/versioning).
- **Linked content** — link any item to any other item across types (e.g. link a note to a related bookmark).
- **Archive & trash** — archive items to hide them from default views, or soft-delete to trash with 30-day recovery.
- **Full-text search** — all fields are searchable. See [Search](/docs/features/search).
- **AI suggestions** — Pro accounts get AI-powered suggestions for tags, titles, descriptions, relationships, and prompt arguments. See [AI Features](/docs/features/ai).

> [!tip]
> All content types support optimistic locking — if someone else (or another tool via MCP) edits the same item while you're working on it, you'll see a conflict dialog with options to keep your version or load the latest.
