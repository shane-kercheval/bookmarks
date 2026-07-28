/**
 * Hand-curated metadata for `/docs/*` pages, used by the command palette to
 * make docs findable by both title and body-content keywords.
 *
 * Each entry's `searchText` is a keyword-rich summary (not prose) optimized
 * for substring search — terms a user might type when looking for that page.
 * Keep the keywords dense; drift here is graceful (a missing term yields a
 * missed palette result, not a broken feature), but compounding drift erodes
 * discoverability over time.
 *
 * MAINTENANCE: when you add a `/docs/*` page or substantially change an
 * existing one, update the corresponding entry here. `AGENTS.md`'s
 * "Files to Keep in Sync" section calls this out as a tracked obligation.
 *
 * Order in this array is the display order in the palette under the Docs
 * group (which itself sits between Settings and Tips).
 */
import type { ReactNode } from 'react'
import { HelpIcon } from '../components/icons'

export interface DocsRoute {
  /** Path that matches an entry in `routePrefetch.ts`. */
  path: string
  /** Display label in the palette. Prefixed `Docs:` consistently. */
  label: string
  /** Keyword-rich summary matched alongside `label` (case-insensitive substring). */
  searchText: string
}

export const DOCS_ROUTES: DocsRoute[] = [
  {
    path: '/docs',
    label: 'Docs: Overview',
    searchText:
      'documentation overview home index help guides reference welcome getting started '
      + 'features ai integration extensions cli api',
  },
  {
    path: '/docs/features',
    label: 'Docs: Features',
    searchText:
      'features overview content types bookmarks notes prompts templates tags filters '
      + 'collections search versioning history keyboard shortcuts hotkeys',
  },
  {
    path: '/docs/features/content-types',
    label: 'Docs: Content Types',
    searchText:
      'content types bookmarks notes prompts url scraping metadata title description '
      + 'page content article parser pdf markdown editor jinja templates slash commands '
      + 'command menu cmd+/ reading mode cmd+shift+m tags shared global archive trash '
      + 'deleted soft delete versioning relationships linked content optimistic locking '
      + 'conflict quick add paste cmd+v ctrl+v shift+cmd+click silent open last used',
  },
  {
    path: '/docs/features/prompts',
    label: 'Docs: Prompts & Templates',
    searchText:
      'prompts templates jinja jinja2 variables placeholders double brace arguments '
      + 'required optional default render mcp api skill agent skills tags slash commands '
      + 'variable if block conditionals if endif loops for filter pipe upper join default '
      + 'whitespace control strip trim minus dash strict mode undefined error typo '
      + 'render endpoint reusable',
  },
  {
    path: '/docs/features/tags-filters',
    label: 'Docs: Tags & Filters',
    searchText:
      'tags filters saved filters collections boolean expressions and or groups '
      + 'and group or group content type bookmarks notes prompts default sort sidebar '
      + 'drag drop reorder rename delete inline editing autocomplete suggestions usage '
      + 'count global namespace case insensitive shared across types all bookmarks '
      + 'all notes all prompts archive trash',
  },
  {
    path: '/docs/features/search',
    label: 'Docs: Search',
    searchText:
      'search full text search substring matching stemming relevance ranking scoring '
      + 'fields title description content url two tier weight focus slash global search '
      + 'command palette cmd+shift+p operators quoted phrase exact match minus exclude '
      + 'negation OR operator combine tags AND any all in-content search literal '
      + 'case sensitive context lines',
  },
  {
    path: '/docs/features/versioning',
    label: 'Docs: Versioning',
    searchText:
      'versioning version history audit trail restore previous diff timeline v1 v2 '
      + 'content versions create update restore audit events delete undelete archive '
      + 'unarchive history sidebar cmd+shift+\\ ctrl+shift+\\ source web mcp api iphone '
      + 'retention free pro days max versions limit changes change tracking',
  },
  {
    path: '/docs/features/shortcuts',
    label: 'Docs: Keyboard Shortcuts',
    searchText:
      'keyboard shortcuts hotkeys keybindings cmd ctrl command palette search shortcuts '
      + 'dialog navigation view markdown editor bold italic strikethrough highlight '
      + 'blockquote inline code code block bullet list numbered list checklist link '
      + 'horizontal rule reading mode toggle word wrap line numbers monospace font '
      + 'table of contents toc sidebar slash menu save save and close history sidebar '
      + 'paste url select next occurrence multi cursor',
  },
  {
    path: '/docs/features/ai',
    label: 'Docs: AI Features',
    searchText:
      'ai features pro plan tag suggestions sparkle metadata generation title description '
      + 'relationship discovery linked content argument suggestions prompt arguments '
      + 'placeholder byok bring your own key api key google openai anthropic gemini '
      + 'model selection rate limits configuration auto fill generate',
  },
  {
    path: '/docs/ai',
    label: 'Docs: AI Integration',
    searchText:
      'ai integration mcp model context protocol claude code claude desktop codex '
      + 'antigravity agy gemini google cursor windsurf chatgpt connect ai assistants agents setup configure tokens '
      + 'example prompts widget tools server oauth connector custom connector paste url '
      + 'sign in browser login no token authorize consent mobile ios sync plugins '
      + 'browse plugins openid known issue problem connecting authenticate',
  },
  {
    path: '/docs/cli',
    label: 'Docs: CLI',
    searchText:
      'cli command line tool tiddly install login oauth pat authentication mcp configure '
      + 'skills bookmarks notes prompts quick start curl bash claude code codex '
      + 'claude desktop terminal shell command',
  },
  {
    path: '/docs/cli/mcp',
    label: 'Docs: CLI MCP Setup',
    searchText:
      'cli mcp setup configure tools claude code claude desktop codex tokens servers '
      + 'content prompts dedicated tokens per tool scope user directory project flag '
      + 'dry run force overwrite expires expiration delete remove status detection '
      + 'config file json toml claude_desktop_config codex multi account preserved '
      + 'work_prompts custom entries mismatch safety',
  },
  {
    path: '/docs/cli/skills',
    label: 'Docs: CLI Skills',
    searchText:
      'cli skills configure list agent skills export prompt templates skill md '
      + 'skill markdown agent skills standard agentskills tag skill tags tag match '
      + 'all any filter claude code codex claude desktop scope user directory '
      + 'tar.gz extract install update auto invoke slash command natural language '
      + 'constraints name length description multi line',
  },
  {
    path: '/docs/cli/reference',
    label: 'Docs: CLI Reference',
    searchText:
      'cli reference commands login logout oauth pat personal access token bm_ '
      + 'device code flow auth status keyring credentials file fallback xdg config '
      + 'token resolution priority env environment variable tiddly_token tokens list '
      + 'create delete export json backup include archived config api url update check '
      + 'completions bash zsh fish tab completion status path '
      + 'ai-instructions ai agent instructions llms first command',
  },
  {
    path: '/docs/extensions',
    label: 'Docs: Browser Extensions',
    searchText:
      'browser extensions chrome safari brave edge arc chromium save bookmarks scrape '
      + 'metadata search popup toolbar one click add',
  },
  {
    path: '/docs/extensions/chrome',
    label: 'Docs: Chrome Extension',
    searchText:
      'chrome extension brave edge arc chromium install web store setup sign in session '
      + 'sync automatic login no token clerk pat personal '
      + 'access token fallback pin toolbar configure save bookmark search tab default tags '
      + 'pre-tag shortcut alt option shift s keyboard rebind chrome://extensions/shortcuts '
      + 'popup auto fill scrape metadata full text duplicate detection existing bookmark '
      + 'search recent bookmarks filter sort relevance last used',
  },
  {
    path: '/docs/extensions/safari',
    label: 'Docs: Safari Extension',
    searchText:
      'safari extension macos ios ipados iphone ipad apple native coming soon planned '
      + 'browser',
  },
  {
    path: '/docs/api',
    label: 'Docs: API',
    searchText:
      'api rest http endpoints bookmarks notes prompts content tags history '
      + 'authentication bearer token personal access token pat bm_ swagger openapi '
      + 'try it out pagination offset limit sorting tag filtering optimistic locking '
      + 'if-unmodified-since archive trash relationships rate limits headers '
      + 'x-ratelimit x-request-source request source audit telemetry '
      + 'ai endpoints auth0 jwt programmatic',
  },
  {
    path: '/docs/tips',
    label: 'Docs: Tips',
    searchText:
      'tips list browse search keyword filter category audience beginner power user '
      + 'getting started learn productivity tricks shortcuts features discoverability '
      + 'how to guide',
  },
  {
    path: '/docs/faq',
    label: 'Docs: FAQ',
    searchText:
      'faq frequently asked questions help support troubleshooting how does '
      + 'clicking content list bookmarks notes prompts filter collection sidebar '
      + 'tags rename delete inactive archive trash difference version history '
      + 'restore retention plan free pro relationships content limit storage '
      + 'search operators ai suggestions byok personal access tokens pat secure '
      + 'mcp integration claude codex desktop skills prompt templates variables',
  },
  {
    path: '/docs/known-issues',
    label: 'Docs: Known Issues',
    searchText:
      'known issues bugs limitations expected behavior workarounds text content '
      + 'image file attachment markdown image syntax external loose list extra '
      + 'line break codemirror editor word wrap shift arrow selection wrapped '
      + 'lines stuck find replace flicker toolbar checkbox',
  },
]

/** Display icon for every docs entry in the command palette. */
export function getDocsIcon(): ReactNode {
  return <HelpIcon className="h-4 w-4" />
}
