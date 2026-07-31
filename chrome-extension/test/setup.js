import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { setupDOM } from '../popup-core.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// --- In-memory Chrome storage ---

let storageData = {};

function resetChromeStorage() {
  storageData = {};
}

// --- Chrome API mock ---

function createChromeMock() {
  return {
    storage: {
      // storage.session backs the popup's auth-mode snapshot (mode flags
      // only). Tests seed it via chrome.storage.session.get mocks per test;
      // the default (empty) means "no snapshot" — the live-probe path.
      session: {
        get: vi.fn().mockResolvedValue({}),
        set: vi.fn().mockResolvedValue(undefined),
        remove: vi.fn().mockResolvedValue(undefined),
      },
      local: {
        get: vi.fn((keys) => {
          const result = {};
          for (const key of keys) {
            if (key in storageData) {
              result[key] = structuredClone(storageData[key]);
            }
          }
          return Promise.resolve(result);
        }),
        set: vi.fn((items) => {
          Object.assign(storageData, structuredClone(items));
          return Promise.resolve();
        }),
        remove: vi.fn((keys) => {
          for (const key of keys) {
            delete storageData[key];
          }
          return Promise.resolve();
        }),
      },
    },
    runtime: {
      // Real MV3 sendMessage always returns a Promise; default to one so
      // callers that do `.catch()` on the return don't throw when a test
      // hasn't set a specific mock.
      sendMessage: vi.fn(() => Promise.resolve(undefined)),
      openOptionsPage: vi.fn(),
      id: 'test-extension-id',
      onMessage: { addListener: vi.fn() },
    },
    tabs: {
      query: vi.fn(),
      create: vi.fn(),
    },
    scripting: {
      executeScript: vi.fn(),
    },
    // The Clerk SDK reads the sync-host session cookie through this API.
    // Unit tests mock the SDK itself, but the surface must exist so any
    // unmocked code path fails loudly rather than on a missing namespace.
    cookies: {
      get: vi.fn().mockResolvedValue(null),
      getAll: vi.fn().mockResolvedValue([]),
    },
  };
}

// --- setupPopupDOM: reads real popup.html and calls setupDOM ---

function setupPopupDOM() {
  const html = fs.readFileSync(path.join(__dirname, '..', 'popup.html'), 'utf-8');
  document.body.innerHTML = html;

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
}

// --- mockMessages helper ---

// The four authenticated data operations MUST carry expectedPrincipal — the
// real worker fails closed without it. The mock throws loudly if one omits it,
// so a wiring mistake (a handler/caller that drops the field) fails a test
// instead of hiding behind a canned success — exactly the gap that let two
// whole-feature breaks pass a green suite. Tests that deliberately exercise the
// missing-principal path pass `{ allowMissingPrincipal: true }`.
const PRINCIPAL_BOUND_MESSAGES = new Set([
  'GET_LIMITS', 'GET_TAGS', 'SEARCH_BOOKMARKS', 'CREATE_BOOKMARK',
]);

function mockMessages(responses, { allowMissingPrincipal = false } = {}) {
  globalThis.chrome.runtime.sendMessage.mockImplementation((msg) => {
    // Mirrors the real fail-closed condition exactly (!expectedPrincipal):
    // absent, undefined, null, and '' all fail — not just a missing property.
    if (!allowMissingPrincipal
        && PRINCIPAL_BOUND_MESSAGES.has(msg.type)
        && !msg.expectedPrincipal) {
      throw new Error(
        `${msg.type} sent without a usable expectedPrincipal — the real worker fails closed. ` +
        `Establish currentPrincipal before this request, or pass allowMissingPrincipal to test the omission.`
      );
    }
    const response = responses[msg.type];
    if (response instanceof Error) {
      return Promise.reject(response);
    }
    // A real success can only exist when the resolved principal matched the
    // request's expectedPrincipal, and the envelope always echoes it. Stamp
    // that invariant onto success fixtures that don't set it explicitly, so
    // consumers exercising serving-principal checks (e.g. the cache-write
    // gate) see production-faithful responses. Fixtures may still override
    // `principal` explicitly to simulate a drifted server response.
    if (response?.success && PRINCIPAL_BOUND_MESSAGES.has(msg.type) && !('principal' in response)) {
      return Promise.resolve({ ...response, principal: msg.expectedPrincipal });
    }
    return Promise.resolve(response ?? null);
  });
}

// --- Install Chrome mock globally before each test ---

beforeEach(() => {
  resetChromeStorage();
  globalThis.chrome = createChromeMock();
  window.matchMedia = vi.fn((query) => ({ matches: false, media: query }));
});

export { resetChromeStorage, setupPopupDOM, mockMessages };
