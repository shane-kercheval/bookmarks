import {
  setupDOM, pickDefaultTab, setPopupMode, activateTab, setTabEnabled,
  isRestrictedPage, initSaveForm, initSearchView,
} from './popup-core.js';

setupDOM({
  loadingView: document.getElementById('loading-view'),
  setupView: document.getElementById('setup-view'),
  saveView: document.getElementById('save-view'),
  searchView: document.getElementById('search-view'),
  popupHeader: document.getElementById('popup-header'),
  tabSave: document.getElementById('tab-save'),
  tabSearch: document.getElementById('tab-search'),
  settingsBtn: document.getElementById('settings-btn'),
  saveForm: document.getElementById('save-form'),
  loadingIndicator: document.getElementById('loading-indicator'),
  urlInput: document.getElementById('url'),
  titleInput: document.getElementById('title'),
  descriptionInput: document.getElementById('description'),
  titleLimit: document.getElementById('title-limit'),
  descriptionLimit: document.getElementById('description-limit'),
  tagsInput: document.getElementById('tags-input'),
  tagChipsContainer: document.getElementById('tag-chips'),
  tagSuggestions: document.getElementById('tag-suggestions'),
  saveBtn: document.getElementById('save-btn'),
  saveStatus: document.getElementById('save-status'),
  clearTagsBtn: document.getElementById('clear-tags'),
  searchInput: document.getElementById('search-input'),
  searchResults: document.getElementById('search-results'),
  searchLoading: document.getElementById('search-loading'),
  loadMoreBtn: document.getElementById('load-more'),
  searchTagInput: document.getElementById('search-tag-input'),
  searchTagDropdown: document.getElementById('search-tag-dropdown'),
  searchSortSelect: document.getElementById('search-sort-select'),
  searchActiveTags: document.getElementById('search-active-tags'),
});

document.getElementById('settings-btn').addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});

// Lazy-init guards: the popup DOM is destroyed on blur, so flags reset on every reopen.
// Prevents duplicated listeners when the user switches Save → Search → Save within one open.
let saveInitialized = false;
let searchInitialized = false;
let currentTab = null;
// Resolves to the LIVE auth status (carrying the authoritative principal) —
// the shell renders from the snapshot, but user-scoped cached content
// (draft/tags) hydrates only against this fresh principal, so a stale snapshot
// can never surface a previous account's data. Set once in init().
let freshStatusPromise = null;

async function activateAndInit(name, { stealFocus = true } = {}) {
  activateTab(name);
  if (name === 'save' && !saveInitialized) {
    saveInitialized = true;
    await initSaveForm(currentTab, { focus: stealFocus, statusPromise: freshStatusPromise });
  } else if (name === 'search' && !searchInitialized) {
    searchInitialized = true;
    await initSearchView({ focus: stealFocus, statusPromise: freshStatusPromise });
  }
}

function wireTabClicks() {
  for (const name of ['save', 'search']) {
    const tab = document.getElementById(`tab-${name}`);
    tab.addEventListener('click', () => {
      if (tab.getAttribute('aria-disabled') === 'true') return;
      activateAndInit(name);
    });
  }
  // Roving tabindex: arrow keys move between enabled tabs, skipping disabled.
  const tablist = document.querySelector('[role="tablist"]');
  tablist.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const order = ['save', 'search'];
    const activeName = document.activeElement?.id?.replace('tab-', '');
    if (!order.includes(activeName)) return;
    const direction = e.key === 'ArrowRight' ? 1 : -1;
    for (let i = 1; i <= order.length; i++) {
      const idx = (order.indexOf(activeName) + direction * i + order.length) % order.length;
      const candidate = document.getElementById(`tab-${order[idx]}`);
      if (candidate.getAttribute('aria-disabled') !== 'true') {
        candidate.focus();
        // Preserve WAI-ARIA roving-tabindex: focus stays on the tab button so the
        // user can keep arrow-navigating; they explicitly Tab out to enter the panel.
        activateAndInit(order[idx], { stealFocus: false });
        e.preventDefault();
        return;
      }
    }
  });
}

async function init() {
  // Auth state comes from the background worker (session or PAT — the popup
  // never sees tokens, only status). Deciding from storage.local.token alone
  // would show session-synced users the paste-a-token onboarding screen.
  //
  // Snapshot-first render: the worker persists mode flags (never tokens) to
  // storage.session after every status resolution, so subsequent opens render
  // instantly instead of waiting out a cold Clerk initialization. Only an
  // authed snapshot is trusted optimistically — a "none" snapshot defers to a
  // live probe (the loading view holds), so a user who just signed in on the
  // web is never wrongly shown the setup screen.
  //
  // The snapshot renders only the SHELL (which view) instantly. Account
  // content — draft text, tags — never hydrates from it: the view init awaits
  // the live status (freshStatusPromise) and reads only the fresh principal's
  // cache partition, so a stale snapshot can surface the wrong shell for at
  // most one open but never another account's data. The background refresh
  // updates the snapshot for the NEXT open; do not re-render the current one
  // when it resolves — yanking the shell mid-interaction is worse than a
  // one-open stale shell, and content is already principal-gated regardless.
  let status = null;
  try {
    const { authSnapshot } = await chrome.storage.session.get(['authSnapshot']);
    if (authSnapshot && authSnapshot.activeMode !== 'none') {
      status = authSnapshot;
      // The live refresh doubles as the fresh-principal source for content
      // hydration (initSaveForm awaits it); this shell renders from the
      // snapshot now and doesn't wait.
      freshStatusPromise = chrome.runtime.sendMessage({ type: 'GET_AUTH_STATUS' }).catch(() => null);
    }
  } catch {
    // storage.session unavailable — fall through to the live probe.
  }
  if (!status) {
    freshStatusPromise = chrome.runtime.sendMessage({ type: 'GET_AUTH_STATUS' }).catch(() => null);
    status = await freshStatusPromise;
  }

  if (!status || status.activeMode === 'none') {
    setPopupMode('setup');
    // Primary path is the M7 headline: sign in on the web, the extension
    // follows automatically. The token is the secondary, explicit fallback.
    const signInBtn = document.getElementById('sign-in-btn');
    signInBtn.addEventListener('click', () => {
      chrome.tabs.create({ url: 'https://tiddly.me' });
    });
    document.getElementById('open-options').addEventListener('click', () => {
      chrome.runtime.openOptionsPage();
    });
    signInBtn.focus();
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tab;

  setPopupMode('app');
  wireTabClicks();

  const restricted = isRestrictedPage(tab?.url);
  setTabEnabled('save', !restricted, restricted ? "Save — this page can't be bookmarked" : undefined);

  const defaultTab = pickDefaultTab({ url: tab?.url, hasToken: true });
  await activateAndInit(defaultTab);
}

init().catch(() => {
  document.getElementById('popup').textContent = 'Something went wrong. Try reopening the extension.';
});
