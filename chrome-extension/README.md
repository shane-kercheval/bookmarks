# Tiddly Bookmarks Chrome Extension

Save bookmarks to [tiddly.me](https://tiddly.me) with one click. Search your bookmarks from the new tab page.

## Features

- **One-click save** — click the extension icon on any page to save it as a bookmark with title, description, tags, and page content (for search)
- **Tag selection** — pre-filled from your defaults and last-used tags, with selectable chips from your existing tags
- **Search** — on restricted pages (new tab, chrome://, etc.), search your bookmarks instead
- **PAT authentication** — uses Personal Access Tokens

## Setup

### 1. Build and install the extension

The loadable extension is a *built artifact*, not the source tree (the service worker is bundled and the manifest is generated per environment). On a fresh checkout, install dependencies first:

```bash
make chrome-ext-install     # or: cd chrome-extension && npm install
cd chrome-extension
node build.mjs production   # → build/production/
```

1. Open `chrome://extensions/` in Chrome
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select `chrome-extension/build/production/`

### 2. Create a Personal Access Token

1. Go to [tiddly.me/app/settings/tokens](https://tiddly.me/app/settings/tokens)
2. Create a new token
3. Copy the token (starts with `bm_`)

### 3. Configure the extension

1. Right-click the extension icon > **Options** (or click the gear icon)
2. Paste your PAT
3. Optionally set default tags (comma-separated, e.g. `reading-list, chrome`)
4. Click **Test Connection** to verify
5. Click **Save**

## Usage

**Saving a bookmark:** Click the extension icon on any webpage. Review the pre-filled form (URL, title, description, tags) and click **Save Bookmark**.

### Keyboard shortcut

The extension suggests a default shortcut to open the popup:

- **Mac:** `Option+Shift+S`
- **Windows / Linux / ChromeOS:** `Alt+Shift+S`

Chrome only auto-binds this on a fresh install, and silently leaves the shortcut unset if another extension already claimed the same combination (no error message). If the shortcut doesn't open the popup, open `chrome://extensions/shortcuts` and bind (or rebind) **Tiddly Bookmarks → Activate the extension** to a combination of your choice.

**Searching bookmarks:** Click the extension icon on a new tab or restricted page. Type to search, or browse your recent bookmarks.

## Testing

```bash
make chrome-ext-install   # Install dependencies (esbuild + vitest + jsdom)
make chrome-ext-tests     # Run tests
```

## Store Assets

Marketing images for the Chrome Web Store listing live in `store-assets/`:

- `src/` — raw popup screenshots (drop new captures here)
- `build.py` — Pillow-based composer
- `out/` — generated assets at the exact dimensions Google requires

Regenerate after tweaking copy, colors, or source screenshots:

```bash
cd chrome-extension/store-assets
uv run --with pillow python build.py
```

Outputs:

| File | Size | Slot |
|---|---|---|
| `screenshot-save-1280x800.png` | 1280×800 | Screenshot (required) |
| `screenshot-search-1280x800.png` | 1280×800 | Screenshot (required) |
| `promo-small-440x280.png` | 440×280 | Small promo tile (required) |
| `promo-marquee-1400x560.png` | 1400×560 | Marquee (optional, used if Google features the listing) |

`store-assets/` is not included in `make chrome-ext-zip` — it stays out of the uploaded bundle.

## Releasing a New Version

Full workflow for publishing an update to the Chrome Web Store:

1. **Finish all code changes and merge to `main`.** Run `make chrome-ext-verify` locally; all tests must pass.
2. **Bump the version** in `manifest.base.json` (the committed template; the built manifests inherit it). Chrome Web Store rejects re-uploads of an existing version. Use semver (patch for bug fixes, minor for user-visible changes, major for breaking/removed features).
3. **Regenerate store assets** if the UI changed or copy needs updating (see *Store Assets* above).
4. **Commit the version bump and any asset changes** and push.
5. **Build the upload zip:**
   ```bash
   make chrome-ext-zip
   # -> dist/chrome-extension.zip
   ```
6. **Upload to the Developer Dashboard:** https://chrome.google.com/webstore/devconsole
   - Open the **Tiddly Bookmarks** item
   - **Package** tab → **Upload new package** → select `dist/chrome-extension.zip`
   - The dashboard parses `manifest.json` and rejects the upload if the version didn't actually increment
7. **Update the store listing** on the same item's **Store listing** tab:
   - Replace screenshots with `store-assets/out/screenshot-*.png`
   - Replace the small promo tile with `store-assets/out/promo-small-440x280.png`
   - (Optional) Update the marquee with `store-assets/out/promo-marquee-1400x560.png`
   - Update the description if user-visible behavior changed
8. **Submit for review.** Review time ranges from a few hours to a few days; longer if `permissions` / `host_permissions` in `manifest.json` changed. Adding new permissions or broadening host patterns triggers a deeper review.
9. **Monitor the listing** for approval or rejection emails. On rejection, fix + re-upload under the same (already-bumped) version number — Google tracks per-submission, not per-version, for retries before publication.

### Common gotchas

- Screenshot dimensions must match exactly (1280×800, not 1279×800). The composer enforces this.
- Keyword stuffing in the description is a common rejection reason — keep it conversational.
- `"Test Connection"` buttons, debug toggles, or other development affordances visible in the UI can trigger rejection as "not ready for users." Double-check the Options page before zipping.

## Local Development

To develop against a local API server, build the development artifact — it points at `http://localhost:8000` (config and manifest `host_permissions` together) with no source edits:

```bash
cd chrome-extension
node build.mjs development   # → build/development/
```

Load `build/development/` unpacked, and rebuild + reload after code changes. To override the defaults, copy `.env.template` to `.env.development.local` / `.env.production.local` — those exact names; they're gitignored, and real environment values must never be committed. Production env files are for production-specific values (later: Clerk keys); `TIDDLY_API_URL` itself is pinned in production — a different API origin means adding a distinct build mode, not overriding production.
