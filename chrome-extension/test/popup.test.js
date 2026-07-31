import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { mockMessages as strictMockMessages } from './setup.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const POPUP_HTML = fs.readFileSync(path.join(__dirname, '..', 'popup.html'), 'utf-8');

const VALID_LIMITS = {
  max_title_length: 100,
  max_description_length: 1000,
  max_bookmark_content_length: 100000,
};

function setStorage(values) {
  chrome.storage.local.get.mockImplementation((keys) => {
    const result = {};
    for (const key of keys) {
      if (key in values) result[key] = values[key];
    }
    return Promise.resolve(result);
  });
}

function setTab(tab) {
  chrome.tabs.query.mockResolvedValue(tab ? [tab] : []);
}

// Unless a test overrides it, app-mode tests run as a PAT-configured user —
// the pre-Clerk baseline, with a deterministic principal so hydration and
// request binding behave as production would. Delegates to the SHARED strict
// mock (setup.js), which throws on any authenticated message lacking a usable
// expectedPrincipal — the detector that the local, permissive copy of this
// helper previously lacked, letting broken request wiring pass as green.
const DEFAULT_PRINCIPAL = 'pat:popuptest0000000';

function mockMessages(responses, opts) {
  strictMockMessages({
    GET_AUTH_STATUS: { activeMode: 'pat', hasPat: true, hasSession: false, principal: DEFAULT_PRINCIPAL },
    ...responses,
  }, opts);
}

function mockPageScrape(data = {}) {
  chrome.scripting.executeScript.mockResolvedValue([{
    result: {
      title: data.title ?? 'Page Title',
      description: data.description ?? '',
      content: data.content ?? '',
    },
  }]);
}

async function runPopup() {
  document.body.innerHTML = POPUP_HTML;
  vi.resetModules();
  await import('../popup.js');
  // Yield twice so the top-level async init() chain settles.
  await new Promise(r => setTimeout(r, 0));
  await new Promise(r => setTimeout(r, 0));
}

describe('popup controller — setup state', () => {
  it('no token: shows setup-view and hides the tabbed header', async () => {
    setStorage({});
    setTab(null);
    await runPopup();

    expect(document.getElementById('setup-view').hidden).toBe(false);
    expect(document.getElementById('popup-header').hidden).toBe(true);
    expect(document.getElementById('save-view').hidden).toBe(true);
    expect(document.getElementById('search-view').hidden).toBe(true);
  });

  it('no auth: does not call initSaveForm or initSearchView (no API fetches)', async () => {
    setStorage({});
    setTab(null);
    await runPopup();

    // The status probe itself is expected; no data-fetching messages may fire.
    const nonAuthCalls = chrome.runtime.sendMessage.mock.calls.filter(
      c => c[0].type !== 'GET_AUTH_STATUS'
    );
    expect(nonAuthCalls).toEqual([]);
    expect(chrome.scripting.executeScript).not.toHaveBeenCalled();
  });

  // Keyboard-only first-run flow — Enter on the setup view should launch the
  // PRIMARY path (sign in on the web; the extension follows automatically).
  it('no auth: focuses the sign-in button, and both CTAs work', async () => {
    setStorage({});
    setTab(null);
    await runPopup();

    const signInBtn = document.getElementById('sign-in-btn');
    expect(document.activeElement).toBe(signInBtn);

    signInBtn.click();
    expect(chrome.tabs.create).toHaveBeenCalledWith({ url: 'https://tiddly.me' });

    document.getElementById('open-options').click();
    expect(chrome.runtime.openOptionsPage).toHaveBeenCalledTimes(1);
  });
});

describe('popup controller — snapshot-first render', () => {
  it('renders instantly from an authed snapshot without awaiting the live probe', async () => {
    setStorage({});
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    chrome.storage.session.get.mockResolvedValue({
      authSnapshot: { activeMode: 'clerk', hasPat: false, hasSession: true },
    });
    // The live probe hangs forever — an instant render must not depend on it.
    const responses = {
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    };
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') return new Promise(() => {});
      return Promise.resolve(responses[msg.type] ?? null);
    });
    await runPopup();

    expect(document.getElementById('popup-header').hidden).toBe(false);
    expect(document.getElementById('setup-view').hidden).toBe(true);
    expect(document.getElementById('loading-view').hidden).toBe(true);
    // The background refresh was still requested (keeps the snapshot fresh
    // for the NEXT open) even though this render never waited on it.
    expect(chrome.runtime.sendMessage.mock.calls.some(c => c[0].type === 'GET_AUTH_STATUS')).toBe(true);
  });

  // Chunk (A) security contract: a stale authed snapshot renders the shell
  // instantly, but user-scoped cached content (draft/tags) is withheld until
  // the FRESH principal is known. If the account is gone or switched, the
  // previous account's draft NEVER surfaces — the shell shows, the fresh probe
  // resolves signed-out, and the form falls to the signed-out path.
  it('stale authed snapshot, auth actually gone: shell renders but the prior draft is withheld and Save shows signed-out', async () => {
    // A cached draft exists under a PREVIOUS owner's partition.
    setStorage({
      'draft:clerk:previousowner0': { url: 'https://example.com', title: 'Prior account draft', description: '', tags: [] },
      'draftImmutable:clerk:previousowner0': { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    chrome.storage.session.get.mockResolvedValue({
      authSnapshot: { activeMode: 'clerk', hasPat: false, hasSession: true },
    });
    // Fresh status resolves signed-out (principal null); data calls fail with
    // the structured flag.
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') {
        return Promise.resolve({ activeMode: 'none', hasPat: false, hasSession: false, principal: null });
      }
      return Promise.resolve({ success: false, error: 'Not signed in', authRequired: true });
    });
    await runPopup();

    // Shell rendered from the snapshot; the prior account's draft is NOT shown.
    expect(document.getElementById('popup-header').hidden).toBe(false);
    expect(document.getElementById('title').value).not.toBe('Prior account draft');
    // And the signed-out truth surfaced (fresh probe → authRequired on data).
    const status = document.getElementById('save-status');
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain('signed out');
  });

  // The direct A→B account switch (the headline attack): A's cached draft is
  // present, the stale snapshot still says authed, but the FRESH principal is a
  // different live account B. A's draft must never render; B reads its own
  // (empty) partition and gets a fresh form.
  it('account switch A→B: A’s cached draft is never shown; B gets a fresh form from its own partition', async () => {
    setStorage({
      'draft:clerk:accountA00000000': { url: 'https://example.com', title: 'Account A secret draft', description: '', tags: ['a-private-tag'] },
      'draftImmutable:clerk:accountA00000000': { url: 'https://example.com', pageContent: 'c', allTags: ['a-private-tag'], limits: VALID_LIMITS },
    });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    chrome.storage.session.get.mockResolvedValue({
      authSnapshot: { activeMode: 'clerk', hasPat: false, hasSession: true },
    });
    // Fresh status resolves to a DIFFERENT live account, B.
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') {
        return Promise.resolve({ activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:accountB00000000' });
      }
      // B's own data (empty draft partition → a fresh form).
      if (msg.type === 'GET_LIMITS') return Promise.resolve({ success: true, data: VALID_LIMITS, principal: 'clerk:accountB00000000' });
      if (msg.type === 'GET_TAGS') return Promise.resolve({ success: true, data: { tags: [] }, principal: 'clerk:accountB00000000' });
      return Promise.resolve(null);
    });
    await runPopup();

    // A's private draft and tags never surface to B.
    expect(document.getElementById('title').value).not.toBe('Account A secret draft');
    expect(JSON.stringify([...document.querySelectorAll('#tag-chips .tag-chip')].map(c => c.textContent)))
      .not.toContain('a-private-tag');
  });

  // The same-account happy path: fresh principal matches the draft owner, so
  // the draft hydrates (a beat after the instant shell).
  it('authed snapshot, same account live: the owner’s cached draft hydrates', async () => {
    setStorage({
      'draft:clerk:owner00000000': { url: 'https://example.com', title: 'My draft', description: '', tags: [] },
      'draftImmutable:clerk:owner00000000': { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    chrome.storage.session.get.mockResolvedValue({
      authSnapshot: { activeMode: 'clerk', hasPat: false, hasSession: true },
    });
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') {
        return Promise.resolve({ activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:owner00000000' });
      }
      return Promise.resolve({ success: true, data: { tags: [] } });
    });
    await runPopup();

    expect(document.getElementById('title').value).toBe('My draft');
  });

  it('does not trust a signed-out snapshot — defers to the live probe', async () => {
    setStorage({});
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    chrome.storage.session.get.mockResolvedValue({
      authSnapshot: { activeMode: 'none', hasPat: false, hasSession: false },
    });
    mockMessages({
      GET_AUTH_STATUS: { activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:sessiononly00000' },
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    });
    await runPopup();

    // The live probe said signed-in — a stale "none" snapshot never forces
    // the setup screen on a user who just signed in on the web.
    expect(document.getElementById('popup-header').hidden).toBe(false);
    expect(document.getElementById('setup-view').hidden).toBe(true);
  });
});

describe('popup controller — loading state', () => {
  // The auth probe can take seconds on a cold worker (Clerk init). Until it
  // resolves, the loading view holds the dialog — and the setup view must
  // never flash for a user who will resolve to signed-in.
  it('shows the loading view while the probe is pending, then swaps once to the app UI', async () => {
    setStorage({});
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    let resolveStatus;
    const gate = new Promise(r => { resolveStatus = r; });
    const responses = {
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    };
    chrome.runtime.sendMessage.mockImplementation(async (msg) => {
      if (msg.type === 'GET_AUTH_STATUS') {
        await gate;
        return { activeMode: 'clerk', hasPat: false, hasSession: true };
      }
      return responses[msg.type] ?? null;
    });

    document.body.innerHTML = POPUP_HTML;
    vi.resetModules();
    const popupDone = import('../popup.js');
    for (let i = 0; i < 4; i++) await new Promise(r => setTimeout(r, 0));

    expect(document.getElementById('loading-view').hidden).toBe(false);
    expect(document.getElementById('setup-view').hidden).toBe(true);
    expect(document.getElementById('popup-header').hidden).toBe(true);

    resolveStatus();
    await popupDone;
    for (let i = 0; i < 4; i++) await new Promise(r => setTimeout(r, 0));

    expect(document.getElementById('loading-view').hidden).toBe(true);
    expect(document.getElementById('setup-view').hidden).toBe(true);
    expect(document.getElementById('popup-header').hidden).toBe(false);
  });

  it('retires the loading view when resolving to the setup screen too', async () => {
    setStorage({});
    setTab(null);
    await runPopup();

    expect(document.getElementById('loading-view').hidden).toBe(true);
    expect(document.getElementById('setup-view').hidden).toBe(false);
  });
});

describe('popup controller — search establishes its own principal', () => {
  // Restricted page → Search is the default view, so it can be the FIRST
  // authenticated path (initSaveForm never runs). It must still establish the
  // fresh principal and bind its requests, or every restricted-page open fails
  // closed with a spurious "account changed".
  it('restricted page (search default): tags and search carry the fresh principal', async () => {
    setStorage({});
    setTab({ id: 1, url: 'chrome://newtab/', title: 'New Tab' });
    const sent = [];
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      sent.push(msg);
      if (msg.type === 'GET_AUTH_STATUS') {
        return Promise.resolve({ activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:searchowner0000' });
      }
      if (msg.type === 'GET_TAGS') return Promise.resolve({ success: true, data: { tags: [] }, principal: 'clerk:searchowner0000' });
      if (msg.type === 'SEARCH_BOOKMARKS') return Promise.resolve({ success: true, data: { items: [], has_more: false }, principal: 'clerk:searchowner0000' });
      return Promise.resolve(null);
    });
    await runPopup();

    const searchMsg = sent.find(m => m.type === 'SEARCH_BOOKMARKS');
    const tagsMsg = sent.find(m => m.type === 'GET_TAGS');
    expect(searchMsg.expectedPrincipal).toBe('clerk:searchowner0000');
    expect(tagsMsg.expectedPrincipal).toBe('clerk:searchowner0000');
    // No spurious account-changed empty state.
    expect(document.querySelector('#search-results .empty-state')?.textContent ?? '')
      .not.toContain('account changed');
  });
});

describe('popup controller — session-synced state (M7 headline)', () => {
  // A user signed in at tiddly.me with NO PAT must get the working app UI,
  // not the paste-a-token onboarding screen (plan M7 step 2 / DoD).
  it('session only, no PAT: shows the app UI, not the setup screen', async () => {
    setStorage({});
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_AUTH_STATUS: { activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:sessiononly00000' },
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    });
    await runPopup();

    expect(document.getElementById('setup-view').hidden).toBe(true);
    expect(document.getElementById('popup-header').hidden).toBe(false);
    expect(document.getElementById('save-view').hidden).toBe(false);
  });

  it('background unreachable (no status response): falls back to the setup screen', async () => {
    setStorage({});
    setTab(null);
    chrome.runtime.sendMessage.mockRejectedValue(new Error('no receiving end'));
    await runPopup();

    expect(document.getElementById('setup-view').hidden).toBe(false);
    expect(document.getElementById('popup-header').hidden).toBe(true);
  });
});

describe('popup controller — default tab selection', () => {
  it('restricted URL: Search is default, Save is disabled with a tooltip', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'chrome://newtab/', title: 'New Tab' });
    mockMessages({
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    const tabSave = document.getElementById('tab-save');
    const tabSearch = document.getElementById('tab-search');
    expect(tabSearch.getAttribute('aria-selected')).toBe('true');
    expect(tabSave.getAttribute('aria-disabled')).toBe('true');
    // a11y: disabled tab's accessible name must still identify the tab as "Save"
    expect(tabSave.getAttribute('aria-label')).toMatch(/^Save\b/);
    expect(tabSave.title).toMatch(/^Save\b/);
    expect(document.getElementById('search-view').hidden).toBe(false);
    expect(document.getElementById('save-view').hidden).toBe(true);
  });

  // Restricted URL → Search auto-route → focus lands on the search input. This
  // assertion exercises searchInput.focus() on the auto-route path.
  it('restricted URL: focuses the search input after auto-routing to Search', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'chrome://newtab/', title: 'New Tab' });
    mockMessages({
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    expect(document.getElementById('tab-save').getAttribute('aria-disabled')).toBe('true');
    expect(document.activeElement).toBe(document.getElementById('search-input'));
  });

  it('regular URL: Save is default, both tabs enabled', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    });
    await runPopup();

    expect(document.getElementById('tab-save').getAttribute('aria-selected')).toBe('true');
    expect(document.getElementById('tab-save').hasAttribute('aria-disabled')).toBe(false);
    expect(document.getElementById('tab-search').hasAttribute('aria-disabled')).toBe(false);
    expect(document.getElementById('save-view').hidden).toBe(false);
  });

  // Regular URL → Save default → focus lands on the Save button. Controller-level
  // counterpart of the popup-core.test.js focus tests; this one exercises the full
  // popup.js boot path including token check and default-tab routing.
  it('regular URL: focuses the Save button after default-tab routing settles', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    });
    await runPopup();

    expect(document.activeElement).toBe(document.getElementById('save-btn'));
  });
});

describe('popup controller — synchronous panel activation', () => {
  it('flips the Save panel visible before initSaveForm awaits finish', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    // Stall page-scrape so initSaveForm's Promise.all never resolves during the test.
    chrome.scripting.executeScript.mockReturnValue(new Promise(() => {}));
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    });

    document.body.innerHTML = POPUP_HTML;
    vi.resetModules();
    const popupDone = import('../popup.js');
    // Yield enough times for the top-level sync path + the storage.get/tabs.query awaits,
    // but initSaveForm's Promise.all will still be pending on scripting.executeScript.
    for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0));

    expect(document.getElementById('save-view').hidden).toBe(false);
    expect(document.getElementById('tab-save').getAttribute('aria-selected')).toBe('true');

    // Clean up — the popup's own init promise will never resolve because we stalled scripting.
    // Swallow the dangling import so vitest doesn't flag an unhandled rejection on teardown.
    popupDone.catch(() => {});
  });
});

describe('popup controller — lazy init idempotency', () => {
  it('clicking the same tab twice does not re-run initSaveForm', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    const limitsCalls = () => chrome.runtime.sendMessage.mock.calls.filter(
      c => c[0].type === 'GET_LIMITS'
    ).length;

    // Save ran at startup (default tab)
    expect(limitsCalls()).toBe(1);

    document.getElementById('tab-search').click();
    await new Promise(r => setTimeout(r, 0));
    document.getElementById('tab-save').click();
    await new Promise(r => setTimeout(r, 0));
    document.getElementById('tab-search').click();
    await new Promise(r => setTimeout(r, 0));

    expect(limitsCalls()).toBe(1);
  });

  // Accessibility fix: arrow-key navigation between tabs must preserve focus
  // on the tab button (WAI-ARIA roving-tabindex pattern), not steal it into the
  // panel input/button. Without the stealFocus: false plumb-through, initSearchView
  // / initSaveForm would focus the panel, breaking subsequent Left/Right arrow
  // navigation because the handler at popup.js:71 returns early when
  // document.activeElement is no longer one of the tab buttons.
  it('ArrowRight from tab-save preserves focus on tab-search rather than stealing into the search input', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    const tabSave = document.getElementById('tab-save');
    tabSave.focus();
    expect(document.activeElement).toBe(tabSave);

    document.querySelector('[role="tablist"]').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })
    );
    await new Promise(r => setTimeout(r, 0));

    expect(document.activeElement).toBe(document.getElementById('tab-search'));
  });

  it('ArrowLeft from tab-search preserves focus on tab-save rather than stealing into Save', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    // Switch to Search via mouse click first so searchInitialized = true.
    document.getElementById('tab-search').click();
    await new Promise(r => setTimeout(r, 0));

    const tabSearch = document.getElementById('tab-search');
    tabSearch.focus();
    expect(document.activeElement).toBe(tabSearch);

    document.querySelector('[role="tablist"]').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true })
    );
    await new Promise(r => setTimeout(r, 0));

    expect(document.activeElement).toBe(document.getElementById('tab-save'));
  });

  // Tab switching back to Search after first init must not re-focus the search
  // input. Once the user has touched the mouse to switch tabs mid-session, focus
  // belongs to them. The searchInitialized guard in popup.js prevents initSearchView
  // from running again, which is what stops the focus call from re-firing.
  it('tab-switch back to Search does not re-focus the search input after first init', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    // Save is the default; first Search click triggers initSearchView and focuses input.
    document.getElementById('tab-search').click();
    await new Promise(r => setTimeout(r, 0));
    expect(document.activeElement).toBe(document.getElementById('search-input'));

    // Spy on subsequent focus calls to prove the guard prevents re-firing.
    const focusSpy = vi.spyOn(document.getElementById('search-input'), 'focus');

    document.getElementById('tab-save').click();
    await new Promise(r => setTimeout(r, 0));
    document.getElementById('tab-search').click();
    await new Promise(r => setTimeout(r, 0));

    expect(focusSpy).not.toHaveBeenCalled();
  });

  it('clicking the disabled Save tab does not run initSaveForm', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'chrome://newtab/', title: 'New Tab' });
    mockMessages({
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
    });
    await runPopup();

    const before = chrome.runtime.sendMessage.mock.calls.length;
    document.getElementById('tab-save').click();
    await new Promise(r => setTimeout(r, 0));

    expect(chrome.runtime.sendMessage.mock.calls.length).toBe(before);
    expect(document.getElementById('tab-search').getAttribute('aria-selected')).toBe('true');
    expect(document.getElementById('search-view').hidden).toBe(false);
  });

  it('Save submit listener only fires once even after multiple tab switches', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
      SEARCH_BOOKMARKS: { success: true, data: { items: [], has_more: false } },
      CREATE_BOOKMARK: { success: true },
    });
    await runPopup();

    document.getElementById('tab-search').click();
    await new Promise(r => setTimeout(r, 0));
    document.getElementById('tab-save').click();
    await new Promise(r => setTimeout(r, 0));

    const createCallsBefore = chrome.runtime.sendMessage.mock.calls.filter(
      c => c[0].type === 'CREATE_BOOKMARK'
    ).length;

    document.getElementById('save-form').dispatchEvent(
      new Event('submit', { cancelable: true, bubbles: true })
    );
    await new Promise(r => setTimeout(r, 0));

    const createCallsAfter = chrome.runtime.sendMessage.mock.calls.filter(
      c => c[0].type === 'CREATE_BOOKMARK'
    ).length;

    expect(createCallsAfter - createCallsBefore).toBe(1);
  });
});

describe('popup controller — settings button', () => {
  it('clicking the settings button calls chrome.runtime.openOptionsPage', async () => {
    setStorage({ token: 'bm_abc' });
    setTab({ id: 1, url: 'https://example.com', title: 'Example' });
    mockPageScrape();
    mockMessages({
      GET_LIMITS: { success: true, data: VALID_LIMITS },
      GET_TAGS: { success: true, data: { tags: [] } },
    });
    await runPopup();

    document.getElementById('settings-btn').click();

    expect(chrome.runtime.openOptionsPage).toHaveBeenCalledTimes(1);
  });
});
