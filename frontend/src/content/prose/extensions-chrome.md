---
route: /docs/extensions/chrome
title: Docs - Chrome Extension
description: Chrome extension setup — install it and sign in at tiddly.me, no tokens needed (Personal Access Token supported as a fallback) — plus the Save tab, Search tab, and keyboard shortcut.
---

# Chrome Extension

Save bookmarks or search your collection from a tabbed popup. The extension auto-scrapes page metadata and captures content for full-text search. A regular webpage opens to the Save tab; a new tab or `chrome://` page opens to the Search tab. You can switch tabs manually at any time.

## Setup

1. **Install the Extension**

   Install from the [Chrome Web Store](https://chrome.google.com/webstore/detail/npjlfgkihebhandkknldnjlcdmcpomkc). Works in Chrome, Edge, Brave, Arc, and other Chromium-based browsers.

2. **Sign in — that's it**

   If you're signed in at [tiddly.me](https://tiddly.me) in the same Chrome profile, the extension connects automatically — no tokens, nothing to configure. Install it while signed in and it just works; if you're signed out, the extension's welcome screen has a sign-in button.

   > [!info]
   > The extension follows your web session: sign out at tiddly.me and the extension signs out too (unless you've added an access token — see below).

3. **Pin the Extension**

   Click the `{{icon:extensions}}` extensions icon in Chrome's toolbar, then click the `{{icon:pin}}` pin icon next to **Tiddly Bookmarks** to add it to your toolbar.

4. **Optional: default tags and access tokens**

   Right-click the `{{icon:bookmark}}` Tiddly Bookmarks icon → **Options** to set default tags that are pre-selected on every save. The same screen accepts a [Personal Access Token](/app/settings/tokens) — optional, used when you're signed out of the web app, or if you prefer a credential you can revoke separately. When both are available, your web session is what's used.

## Save Tab

Click the extension icon on any webpage to open the popup. The Save tab is selected by default on regular pages, with a form pre-filled from the page:

- **URL** — current page URL
- **Title** — from the page title or Open Graph tags
- **Description** — from meta description or Open Graph tags
- **Page content** — body text captured for full-text search (up to your plan's content limit)
- **Tags** — pre-selected from your default tags and recently used tags

Review and edit any field, then click **Save Bookmark**. You can select additional tags from your existing tags shown as chips below the tag input.

> [!info]
> If a bookmark with the same URL already exists (active or archived), you'll see a message with a link to the existing bookmark instead of creating a duplicate.

## Search Tab

Switch to Search from any page, or let the popup default to it on restricted pages like new tabs, `chrome://` pages, or other extension pages (where saving isn't possible — the Save tab is disabled on those).

- Browse your recent bookmarks sorted by creation date
- Type to search across titles, descriptions, URLs, and content
- Filter by tag and sort by created, relevance, last used, modified, or title
- Click a result to open it in a new tab
- Load more results with pagination

## Keyboard shortcut

The extension suggests a default shortcut to open the popup: `{{shortcut:extension.openPopup}}`.

> [!warning]
> Chrome only auto-binds this on a fresh install if no other extension already claims the same combination. If another extension got there first, Chrome silently leaves Tiddly's shortcut unbound — there is no error message. If the shortcut doesn't open the popup, follow the rebind steps below.

### Rebind or change the shortcut

1. Open `chrome://extensions/shortcuts` in a new tab.
2. Find **Tiddly Bookmarks** in the list.
3. Click the pencil icon next to **Activate the extension**.
4. Press the key combination you want.
5. Click **OK**.

## Tips

- **Default tags** — set frequently used tags in the extension settings so they're pre-selected on every save (e.g., `reading-list`).
