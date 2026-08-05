# Editor improvements: reading-mode persistence, ToC in reading mode, callout syntax

Three related improvements to the markdown editor, shipped as one PR:

1. **Reading-mode persistence** — reading mode currently resets to raw markdown on page refresh and on every editor remount triggered by a server sync (conflict refresh, version restore, draft restore, bookmark metadata fetch). It should be remembered per item.
2. **Table of Contents in reading mode** — the ToC toolbar button and shortcut are hidden while reading mode is on, even though a ToC is equally applicable there. Also: add the ToC to the public shared note and prompt views, which currently have no sidebar support. Bookmarks are deliberately excluded from ToC everywhere (rationale in Milestone 2c).
3. **Callout syntax** — support GitHub-style alerts (`> [!WARNING]` etc.) and common variations in the CodeMirror editor, the rendered reading view, and the docs prose pipeline (which already has a narrower callout implementation that this work generalizes rather than duplicates).

All three land in the same subsystem: `ContentEditor` → `CodeMirrorEditor` and the read-only Milkdown preview it hosts in reading mode. Milestones are ordered by dependency: persistence first (it makes reading-mode features testable without the mode resetting underneath you), then ToC, then callouts (independent of the other two, largest diff).

**Required reading before implementing** (beyond the code itself):

- GitHub alerts syntax: https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts
- Obsidian callouts (the `[!note] Custom title` variant we also accept): https://help.obsidian.md/callouts
- CodeMirror 6 decorations: https://codemirror.net/docs/ref/#view.Decoration
- ProseMirror decorations (Milkdown plugins are thin wrappers over these): https://prosemirror.net/docs/ref/#view.Decorations
- mdast (the AST both remark and Milkdown's parser produce; Milestone 3a's shared parser serves an mdast consumer): https://github.com/syntax-tree/mdast

Rationale recorded in this plan for non-obvious decisions must survive into code comments — several existing comments in these files (e.g. the `contentKey` remount notes in `Note.tsx`, the semi-controlled-value note in `CodeMirrorEditor.tsx`) are load-bearing precisely because past decisions were written down at the point of use. Follow that convention.

---

## Milestone 1 — Reading mode survives refresh and server syncs

### Goal & Outcome

Reading mode becomes a remembered, per-item setting instead of transient component state that silently resets.

- Toggling reading mode on a note/bookmark/prompt is remembered for that item: refreshing the page, navigating away and back, or any server-sync remount (conflict resolution, "Load Latest Version", version restore, draft restore, bookmark content fetch) reopens the item in the mode it was left in.
- This includes items whose reading mode was toggled *while being created*: create → toggle reading on → save → refresh restores reading mode.
- An item never toggled opens in markdown (source) mode — the current default.
- Creating a new item always opens in markdown mode with a usable editor (never a blank read-only preview).
- Public shared views are unaffected: they keep opening in reading mode (notes/bookmarks) or raw source (prompts), and a visitor toggling the mode there does not perturb the remembered modes of their own account's items.

### Implementation Outline

**Root cause.** `readingMode` is plain `useState` local to `CodeMirrorEditor` (commented "local, not persisted"). Nothing writes it anywhere (refresh loses it), and the parent components remount the whole editor subtree by bumping `contentKey` — the React `key` on `<ContentEditor>` — whenever server content replaces local content, which re-seeds the state from `defaultReadingMode` (false in the app views).

**Chosen approach: a per-item LRU map in localStorage.** Alternatives considered and rejected:

- *Global preference* (like the existing wrap/line-numbers/mono-font preferences): rejected because one item's mode would leak to all items, including opening the create view as a blank read-only preview, and would regress prompts, which deliberately default to raw source.
- *Small LRU (~10 entries)*: rejected because an eviction here is a visible behavior change ("this note used to open rendered") with an invisible cause. The cap exists as a runaway guard, not a UX mechanism, so it should be large enough that eviction effectively never fires in normal use.

Decisions, all deliberate:

- **Storage**: one localStorage entry holding a map of item ID → entry, capped at **100** entries, least-recently-*used* evicted on overflow. Both a successful read (at editor initialization) and a write refresh an entry's recency — read-refresh matters because an item the user *opens* in reading mode daily but toggled only once must not age out. **Only `readingMode = true` is stored**: toggling an item back to markdown deletes its entry (markdown is the miss-default, so a `false` entry carries no information), which means the cap bounds only meaningful overrides. Follow the key-naming and try/catch-on-storage-errors conventions established by `utils/drafts.ts` and the preference loaders in `ContentEditor.tsx`.
- **Lookup contract**: cache hit → reading mode. Cache miss → markdown mode. No per-type fallback logic; this was explicitly simplified away in design discussion (markdown-on-miss is already what prompts want).
- **Create mode needs no special *seed* case**: a new item has no ID → no cache entry → markdown mode. Do not add one.
- **Create mode does need a *write* case**: if the user toggles reading mode while creating and then saves, the toggle happened before an ID existed, and the create→edit transition deliberately does not remount the editor — so without explicit handling the mode is never written and a later refresh loses it. Handle exactly the `undefined → ID` transition (previous-ID ref local to the editor), but the transition alone is **not sufficient**: navigating from the create view to an *existing* item also delivers an ID in place — the old instance renders once with that item's ID before the parent's corrective `contentKey` remount — and writing on it would poison the existing item's remembered mode with the draft's toggle state (caught in code review). The write therefore additionally requires an explicit create-provenance assertion passed down as a *behavioral* prop (`itemIdWasJustCreated`), which Note/Prompt derive from their existing `fromCreate` contract; the low-level editor must not receive router semantics directly nor infer provenance itself. Record this in a comment at the site.
- **Accepted limitation — bookmark create-toggles are not persisted**: bookmarks have no in-place create→edit transition (create-saves navigate away, and the bookmark editor's key includes the ID, forcing a remount), so they never assert the create signal and a reading-mode toggle made *while creating* a bookmark is lost on save. Accepted: the trigger is narrow (the content editor sits behind a collapsed-by-default panel and is usually auto-scraped, not composed pre-save) and it self-heals on the first toggle after save. Recorded at the Bookmark call site; threading the toggle through the create mutation was considered and rejected as permanent plumbing for a one-time, self-correcting papercut.
- **The reading-mode toggle must reject `disabled` centrally**: the toggle writes durable state, and on a disabled (deleted-item) view `effectiveReadingMode` masks the flip visually — so an unguarded keyboard shortcut would silently mutate the persisted preference. Guard inside the toggle *and* have the capture-phase case decline to consume the event when disabled (matching the file's matcher/handler-symmetry pattern). Do **not** also gate on `readOnly`: toggling on a public-share view is a deliberate visitor feature.
- **Plumbing**: pass the item ID into `ContentEditor` → `CodeMirrorEditor` as an ordinary prop. The warnings in `Note.tsx`/`Prompt.tsx` against using the item ID apply **only** to the React `key` (remount behavior); a plain prop is fine. Seed the reading-mode state from the cache **at state initialization**, not as a live effect — a live override would flip the mode mid-session on the create→edit transition. Because every path that needs the mode re-derived (document switch, server sync) already remounts via `contentKey`, initializer-time seeding plus the transition write above is sufficient. Record this reasoning in a comment at the seed site.
- **Public/reader view isolation**: when `readerMode` is true, neither read from nor write to the cache. Seed from `defaultReadingMode` exactly as today. This preserves the existing split — notes/bookmarks pass `defaultReadingMode={readOnly}`, prompts intentionally omit it so shared templates open as raw source (Jinja syntax is the point of a template; the CodeMirror view has dedicated Jinja highlighting that the rendered view discards). Do not "fix" the prompt inconsistency.
- **Account deletion**: the cache module exports its own clear function, and `AuthProvider.tsx` invokes it as a new discrete `safe('clear-reading-mode-cache', …)` step alongside the existing `clear-drafts` / `clear-byok-keys` steps. Do **not** extend `clearAllDrafts()` — it is prefix-scoped to draft keys and this cache is not a draft.

Whether the mode state continues to live in `CodeMirrorEditor` or moves up to `ContentEditor` alongside the other persisted preferences is the implementer's call after reading the code — the contract above (per-item seed at init, write-through on toggle, the `undefined → ID` transition write, reader-mode isolation) is what matters.

### Definition of Done

- Unit tests for the LRU module: hit/miss; **read refreshes recency** — the decisive sequence is: fill the cache with item A plus 99 others, read A, insert one new entry → A survives and the oldest *untouched* entry is evicted (note: "read A, then insert 100 more" would correctly evict A — that is not a valid survival test); toggle-off deletes the entry; re-toggle reinserts; corrupted/unparseable stored JSON treated as empty (not a crash); storage errors swallowed.
- Component tests (extend `ContentEditorReaderMode.test.tsx` and/or a new file): mode restored after remount with the same item ID (the `contentKey` bump scenario); miss → markdown; no item ID (create mode) → markdown editor is editable; create → toggle on → save (ID appears with the create signal) → remount → reading mode restored; an in-place ID assignment *without* the create signal writes nothing (the `/new` → existing-item poison regression); document switch between two existing items does not cross-write entries; the shortcut on a disabled editor can neither insert nor delete an entry; `readerMode` neither reads nor writes the cache.
- `AuthProvider` account-deletion test asserts the new clear step runs; unit test on the clear function.
- `frontend-verify` passes.

---

## Milestone 2 — Table of Contents in reading mode and on public pages

Scope decisions made during planning, recorded here so implementation doesn't relitigate them:

- **Public-view ToC is in scope for notes and prompts only.** The original ask was to *investigate* feasibility; the investigation happened (the sidebar component is layout-agnostic, the store already treats the ToC panel as session-only, and the real gap is the content-margin handling addressed in 2c).
- **Bookmarks are excluded from ToC entirely** — no app-side ToC (unchanged), no public-side ToC, no ToC wiring in the bookmark component. Rationale in 2c.
- **The editor command menu stays closed in reading mode** — see 2b.

Sub-milestone order is load-bearing: **2a before 2b**. The `!effectiveReadingMode` guards that 2b removes are currently the only thing hiding a control that does not work in reading mode — the scroll target is a hidden CodeMirror view, so heading clicks would silently no-op. Unhiding before fixing ships a visibly broken button.

### 2a — Heading navigation works in reading mode

#### Goal & Outcome

- Clicking a ToC heading while reading mode is on scrolls the rendered view to that heading — including in documents with repeated heading names, setext headings, and headings containing links.
- The scrolled-to heading is not hidden under the sticky header.
- Side benefit for both modes: setext headings appear in the ToC panel, and headings containing links/images display as clean text instead of raw markdown syntax.

#### Implementation Outline

The ToC's `onHeadingClick` flows through `scrollToLineRef`, whose current implementation dispatches a CodeMirror scroll-into-view — a no-op when reading mode has CodeMirror inside a `hidden` wrapper (and its `view.focus()` would be wrong there). Add a reading-mode branch that targets the rendered Milkdown DOM instead. The reading-mode branch must not focus CodeMirror.

**Resolution strategy: candidate-set parity, then ordinal matching, with verification.** The source parser and the rendered DOM must agree on *which* headings exist before index-based matching can be trusted. Naive ordinal matching (and equally, naive same-text occurrence counting) fails whenever one side sees a heading the other doesn't — e.g. `# Usage` / `> # Usage` / `# Usage`: the anchored source regex skips the blockquote-nested heading, but it renders as a real `h1`, so "the 2nd parsed Usage" is the 3rd rendered heading and an index-or-occurrence match lands inside the blockquote. Achieve parity from both directions:

- **Source side** — extend `utils/markdownHeadings.ts` to recognize setext headings (`Title` / `===` → h1, `---` → h2) and ATX headings indented up to 3 spaces (CommonMark-permitted), which remark renders but the current anchored regex skips. Extend `cleanInlineFormatting` to reduce links and images to their text (`[t](u)` → `t`, `![alt](u)` → alt), both so text verification doesn't reject correct targets and because the ToC panel currently displays the raw syntax.
- **Rendered side** — resolve only against *top-level* heading elements (direct children of the ProseMirror document, excluding headings nested in blockquotes/list items — which the source parser also excludes, preserving parity).
- **Safety net** — verify the resolved element's normalized text + level against the parsed heading; on mismatch (residual skew from constructs neither side handles), fall back to selecting the Nth rendered heading with the same normalized text + level, where N is the heading's occurrence index among parsed headings. Record in a comment why parity is required and what the fallback covers.

Reading-mode scrolling moves the page (or nearest scroll container), not a `.cm-scroller` — the heading needs a scroll offset (e.g. `scroll-margin-top`) clearing the sticky header.

#### Definition of Done

- Tests: ordinal resolution scrolls the right element; the adversarial parity case above (duplicate-name heading nested in a blockquote between two top-level duplicates — must reach the correct one); duplicate headings straddling a setext heading; a heading containing a markdown link (verification passes, panel shows clean text); out-of-range ordinal is a safe no-op; markdown-mode path unchanged.
- `markdownHeadings.test.ts` gains the setext, indented-ATX, and link/image-normalization cases.

### 2b — ToC control visible in reading mode

Remove the `!effectiveReadingMode` conditions gating the ToC toolbar button and its capture-phase keyboard shortcut in `CodeMirrorEditor.tsx`. Button active-state and toggle behavior are already wired through the sidebar store.

**The editor command menu (Cmd+/) intentionally stays closed in reading mode.** There is no ToC-specific gate in the menu to remove — the gate is on opening the menu itself, and that same gate is currently the *only* thing preventing the menu's mutating commands (bold, insert link, …) from dispatching real edits into the hidden CodeMirror document: the execute path checks only CodeMirror's `readOnly` state, which is false in ordinary app-side reading mode. Opening the menu in reading mode would therefore require a per-command safety audit for one redundant access path to a feature already reachable via toolbar and shortcut. Keep the gate; record this rationale in a comment at the gate site.

Done = button and shortcut toggle the ToC panel in both modes; a test pins that Cmd+/ does *not* open the command menu in reading mode (intent, not accident); existing toolbar tests updated; `frontend-verify` passes.

### 2c — ToC on public shared note and prompt views

#### Goal & Outcome

- Visitors to a public shared note or prompt can open the ToC sidebar and navigate by heading, in both reading and source modes.
- On desktop, opening the sidebar pushes the content over (no overlay); on mobile the existing full-width panel behavior applies.
- The panel does not persist across page loads, and never leaks onto other public pages (pricing, changelog, roadmap) — neither via a stale in-memory panel nor via panel state persisted from a prior app session.
- Public shared **bookmarks** get no ToC. Rationale, recorded here and in a comment where bookmarks are excluded: bookmark content is scraped with formatting deliberately stripped (it exists to make bookmarks searchable), so it essentially never contains markdown headings — verified empirically against real scraped content, where pages with rich section structure produced zero headings. A bookmark ToC would render its empty state almost always, while requiring from-scratch wiring in the bookmark component plus handling for its collapsed-by-default content panel (ToC open + panel collapsed would orphan the sidebar). The app-side bookmark page already closes the ToC panel on mount ("bookmarks don't support ToC"); that behavior stays. If bookmark authoring habits change, the incremental path is: wire the component → enable public → enable app-side.

#### Implementation Outline

- **Do not put the sidebar margin in `PublicPageLayout`.** That layout wraps pricing, changelog, and roadmap in addition to the three shared-item pages, and the sidebar store can hold panel state those pages must ignore: `history` can be restored from localStorage at store init, and an open `toc` survives client-side navigation (the store has no route cleanup). A layout-level margin keyed on `activePanel !== null` would shift pricing/changelog content ~400px with nothing in the gap. Instead, apply the offset in the shared-item shell (`PublicItemShell` or an equivalent wrapper rendered only by the shared note/prompt pages), conditioned on `activePanel === 'toc'` specifically — never `history`, which no public page can render. Note the layout centers content (`max-w-5xl mx-auto`); the offset must account for centering rather than assuming the app layout's flush-left geometry.
- **Close the ToC when leaving the shared-item pages** (unmount/route-leave), so navigating shared note → pricing doesn't strand an open panel. Precedent for close-on-unsupported-page already exists in the app-side bookmark page.
- Reuse the store's exported `computeMaxWidth` rather than duplicating margin constants; the public layout has no left sidebar, so the ported logic should be simpler than `Layout.tsx`'s, not a copy.
- Then enable `showTocToggle` on the public note and prompt pages (currently explicitly `false`). No changes to the bookmark component or public bookmark page.
- Depends on 2a: public pages open in reading mode by default, so without 2a the control would be visible but broken there.

#### Definition of Done

- Tests: public note/prompt page renders the ToC toggle; opening the panel applies the content offset on desktop; heading click navigates (reading mode); panel absent by default on load; **persisted `history` panel state → public pages render unshifted**; **open ToC on a shared item, navigate to pricing → no offset and panel closed**; public bookmark page has no ToC toggle.
- Manual check of shared note and prompt pages at desktop and mobile widths.
- `frontend-verify` passes.

---

## Milestone 3 — Callout syntax across the rendering pipelines

### Goal & Outcome

Blockquote-style callouts render with an icon, tinted left rule, and (in rendered views) background tint — whether typed by the user, pasted from GitHub, or written by an agent guessing at syntax.

- `> [!WARNING]`, `> [warning]`, `> [!Warning] Custom title` and similar all render as callouts; keyword matching is case-insensitive and the `!` is optional.
- Common aliases map onto five canonical variants:

  | Canonical | Accepted keywords | Color | Icon |
  |---|---|---|---|
  | NOTE | note, info, information | blue | info circle |
  | TIP | tip, hint, success, check, done | green | lightbulb |
  | IMPORTANT | important | purple | exclamation circle |
  | WARNING | warning, attention | amber | warning triangle |
  | CAUTION | caution, danger, error, bug, failure | red | stop octagon |

- Unrecognized keywords (`> [!FOO]`) render as a plain blockquote — fail soft, never break rendering.
- Callouts render in **all three pipelines**: the CodeMirror editor (line-decoration styling, marker text stays visible and editable), the reading-mode rendered view (marker restyled as a title with icon), and the docs prose pipeline. What is shared — and cannot drift — is the marker **grammar and variant resolution** (one module, three consumers), plus the structural rule that a marker is honored only on a blockquote's opening line. Host markdown **block recognition** remains consumer-specific: the editor uses its long-standing line-based approximation, the other two use real markdown ASTs (see the recorded limitation below).
- **The docs pipeline keeps its existing three visual styles** (info/tip/warning). It already renders callouts today via its own remark plugin with a narrower grammar (`!` required, three-way alias collapse); this milestone unifies the *grammar* (what parses as a callout, and which canonical variant it is) while mapping the five canonical variants onto the docs' three existing styles — so no shipped docs page changes appearance. Expanding docs to the five-style palette is a decoupled, deliberately deferred visual decision. Grammar unification slightly broadens what docs accepts (optional `!`, more aliases, inline titles); docs content is curated, so this is harmless.

### Implementation Outline

Three independent rendering pipelines must agree on what counts as a callout, so the parsing/classification logic is a single shared module all three consume — that anti-drift constraint is the reason sub-milestone 3a exists and must come first. The docs pipeline's existing `remarkCallouts.ts` is prior art with its own private grammar; it becomes a consumer of the shared module, not a fourth parser.

### 3a — Shared callout parser

- New pure module (in `utils/`) with a layered contract shaped by its consumers' inputs:
  - **Marker-core**: operates on text *without* the blockquote `>` prefix — because two of the three consumers (ProseMirror decorations, mdast/remark) see post-parse text where the blockquote marker is already consumed. Matches a leading `[!keyword]` / `[keyword]` (case-insensitive, optional bang, optional trailing custom title on the same line), returning the canonical variant, the custom title if any, and the marker's span offsets (so consumers can style or strip exactly the marker).
  - **Raw-source adapter** for CodeMirror: strips the leading `>` and whitespace from a source line and delegates to marker-core, offsetting positions back to line coordinates.
  - **Keyword → canonical-variant resolution** per the alias table above. Unknown keyword → not a callout (`null`), so every consumer falls through to plain-blockquote behavior.
- The mdast-facing usage must be robust to the marker paragraph's *inline structure*: a paragraph's first line isn't always a single text node (a hard line-break after the marker produces `[text, break, text]`). Match against the first paragraph's joined leading inline content, not only `children[0]` — the existing docs plugin has this narrower behavior as a latent wart; the shared module, as the single source of truth, must not inherit it.
- Record in the module docstring *why* it exists (three pipelines, must not drift), the fail-soft rule, and the marker-core/adapter layering rationale (post-parse consumers never see `>`).

**Done**: exhaustive unit tests — every alias × case variations × bang/no-bang × with/without title × leading whitespace; non-matches (no brackets, empty brackets, non-alpha keyword); marker-core positions correct for title styling; the raw-source adapter's offset math. Detection is line-based; whether a mid-quote marker starts a callout is decided by consumers, which only check a block's first line.

### 3b — Callouts in the CodeMirror editor

#### Implementation Outline

- `utils/markdownStyleExtension.ts` currently collapses every `>`-prefixed line into one `blockquote` line type, styled with an indigo left border. Extend the line parser to detect a callout marker via the 3a raw-source adapter, and thread the *current callout variant* through the document walk in `buildDecorations` the same way the existing `inCodeBlock` boolean is threaded — a callout starts at a marker line and its variant applies to subsequent `>` continuation lines until the blockquote ends. This threading pattern is the established convention in that file; do not invent a parallel one.
- Per-variant line classes drive the left-border color and a subtle background tint from the existing theme object, alongside the current blockquote rule.
- **Marker stays visible and editable, styled dim** (like the existing syntax-marker treatment) — this is a live editor; hiding the marker behind a replace decoration fights the cursor. Record this rationale in a comment. Icons in the editor view: at most a modest `::before` on the marker line; if positioning fights the CodeMirror line layout, editor-side icons are droppable — the colored rule is the signal that matters while editing. Ship icons in 3c regardless.

#### Definition of Done

- Tests in the existing `markdownStyleExtension` test file: marker line gets the variant class; continuation lines inherit it; the blockquote ending resets state; a second marker mid-document starts fresh; unknown keyword renders as plain blockquote; callout markers inside fenced code blocks are ignored; adjacent distinct callouts don't bleed into each other.
- No visual regression to plain blockquotes.

### 3c — Callouts in the reading-mode rendered view

#### Implementation Outline

- **Critical shape constraint that drives this design**: in the parsed document, the canonical multi-line form `> [!WARNING]` + `> body` on consecutive quoted lines is **one paragraph** — the marker and the first body line share a paragraph, separated by a soft break (confirmed via the docs pipeline's remark parser, which runs on the same mdast engine Milkdown's parser uses; its marker regex ends `\n?` for exactly this reason). Only the blank-line form (`> [!WARNING]`, `>`, `> body`) yields a separate marker paragraph. Any design that decorates "the marker paragraph" as a title therefore styles body text as title in the most common case. Decorations must be **span-scoped, not paragraph-scoped**.
- **Decoration-only ProseMirror plugin — no schema node, no remark extension.** A `$prose` plugin walks blockquotes, runs the 3a marker-core against the first paragraph's leading inline content, and applies: a node decoration on the blockquote (variant class) and **inline decorations covering only the marker span** (and the custom-title span, if present) within that first paragraph, using the offsets 3a returns. Body text — same-paragraph-after-softbreak or subsequent paragraphs — keeps normal body styling. `MilkdownEditor.tsx` already contains this plugin shape twice (`createCodeBlockCopyPlugin`, `createPlaceholderPlugin`) — follow it.
- Why decoration-only is safe and right here (record in a comment): `MilkdownEditor` has exactly one production consumer — the reading-mode preview inside `CodeMirrorEditor`, always `readOnly` — so there is no editing or serialization path to protect. A real schema node + remark parser/serializer would be several times the code and put markdown round-tripping at risk for zero benefit.
- Styling in `index.css` under the existing `.milkdown-wrapper` scoping: left rule + background tint per variant; the marker span is suppressed/restyled and replaced by a clean title presentation — icon via `::before` on the decorated span, then "Warning" (or the custom title, which the title-span decoration covers). The inline decorations give exact spans, so no CSS heroics against raw text nodes are needed.
- **Icons: inline SVG via CSS `mask-image` data-URIs, colored via `background-color`/`currentColor`** — not emoji (inconsistent cross-platform rendering) and not decoration widgets (heavier, no benefit). Five icons per the table in the milestone goal; heroicons/lucide outlines are fine sources.

#### Definition of Done

- **Fixture tests that assert against the actual Milkdown-parsed document/DOM** — this is the architecture gate for the shape constraint above, not an afterthought: (a) marker + soft-break body on consecutive quoted lines — body text retains body styling and the raw `[!WARNING]` text is not visible as-is; (b) marker + custom title + body; (c) blank-line-separated body (separate paragraphs); (d) marker alone. Plus: each canonical variant gets its class; alias/case spot-checks (exhaustive coverage lives in 3a); unknown keyword → plain blockquote; blockquote with no marker unaffected; marker not at the start of the first paragraph → plain blockquote.
- Visual check of all five variants in reading mode, plus one in the public shared view (same component, but confirm the CSS scoping reaches it).
- `frontend-verify` passes.

### 3d — Docs pipeline adopts the shared grammar

Genuinely small. `components/markdown/remarkCallouts.ts` replaces its private marker regex and three-way alias table with the 3a module (marker-core + canonical resolution), keeping everything else it does today: its mdast surgery (marker stripping, class tagging) and a local five-canonical → three-docs-styles mapping onto the existing `CalloutVariant` type (`note/info/information/important` → info, `tip/hint/success/check/done` → tip, `warning/attention/caution/danger/error/bug/failure` → warning). Record in its docstring that the grammar is shared and the 3-style collapse is a deliberate docs presentation choice. Done = existing docs markdown tests stay green (no visual change to shipped pages); new spot-checks through the remark path for the broadened grammar (`[!danger]` → docs warning, optional-`!` accepted); `frontend-verify` passes.

---

## Recorded limitation & follow-up — editor line-model vs. AST block recognition

The CodeMirror styling layer (`utils/markdownStyleExtension.ts`) approximates markdown block structure per line, by long-standing design — this predates callouts and applies to every construct it styles. Callouts are deliberately exactly as approximate as the blockquote styling they extend (making them alone tree-accurate would put callout tinting on lines the editor doesn't even style as quotes). Residual editor/rendered-view differences, all pre-existing line-model limits:

- **Indented blockquotes** (`  > quote`): styled by the rendered views, unstyled (and so un-callouted) in the editor.
- **Tilde fences** (`~~~`): not recognized as code by the styling layer, so a marker inside one is styled in the editor but rendered as code.
- **Lazy continuation** (a `>`-less line continuing a quote): part of the callout in rendered views, unstyled in the editor.
- **Nested-blockquote callouts** (`> > [!tip]`): honored only by the docs pipeline (its visitor is recursive); the editor and reading view treat them as plain quotes.

**Follow-up (deliberately not in this work):** incremental line-parser improvements — tilde-fence tracking and up-to-3-space quote/construct indentation — would narrow the gap for every construct, short of a full syntax-tree-based restyle of the extension (a separate project, if ever). Cross-pipeline tests are scoped accordingly: they pin parity for contiguous explicitly-quoted lines only.

## Cross-cutting notes

- **Keep in sync** (per `AGENTS.md`): callouts are a user-facing markdown capability — check whether the docs prose (`content/prose/*.md`), FAQ, changelog, or `llms-app-usage.txt` mention supported markdown syntax and update accordingly. Reading-mode persistence and public ToC likely warrant a changelog entry.
- **Testing scope**: frontend-only work — run `make frontend-verify`; backend suites are not affected.
- The three milestones are one PR but should remain separately revertible commits in the order above.
