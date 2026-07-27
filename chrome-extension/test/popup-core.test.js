import { resetChromeStorage, setupPopupDOM, mockMessages } from './setup.js';
import {
  SCRAPE_CAP, DRAFT_KEY, DRAFT_IMMUTABLE_KEY,
  isRestrictedPage, isValidLimits, counterText,
  pickDefaultTab, setPopupMode, activateTab, setTabEnabled,
  updateLimitFeedback, updateSaveButtonState, applyLimits,
  truncateByCodePoints,
  setupDOM, resetState,
  saveDraft, clearDraft, getPageData,
  initSaveForm, handleSave, handleSaveError,
  showSaveStatus,
  initSearchView, loadBookmarks,
} from '../popup-core.js';

// NOTE on test coverage scope:
// The injected scraper inside getPageData (popup-core.js around line 350) runs in
// the page context via chrome.scripting.executeScript and is not reachable from this
// harness — tests mock getPageData directly. The injected function inlines the same
// code-point truncation logic as truncateByCodePoints; if you change one, change both.

// --- Test fixtures ---

const VALID_LIMITS = {
  max_title_length: 100,
  max_description_length: 1000,
  max_bookmark_content_length: 100000,
};

const VALID_TAGS = ['javascript', 'python', 'rust', 'go', 'typescript', 'react', 'vue', 'svelte', 'node'];

function validLimitsResponse() {
  return { success: true, data: VALID_LIMITS };
}

function validTagsResponse() {
  return { success: true, data: { tags: VALID_TAGS.map(name => ({ name })) } };
}

function makeTab(url = 'https://example.com') {
  return { id: 1, url, title: 'Example' };
}

function mockPageData(data = {}) {
  chrome.scripting.executeScript.mockResolvedValue([{
    result: {
      title: data.title ?? 'Page Title',
      description: data.description ?? 'Page description',
      content: data.content ?? 'Page content',
    }
  }]);
}

// --- Pure function tests ---

describe('isRestrictedPage', () => {
  it('returns true for chrome:// URLs', () => {
    expect(isRestrictedPage('chrome://extensions')).toBe(true);
  });

  it('returns true for about: URLs', () => {
    expect(isRestrictedPage('about:blank')).toBe(true);
  });

  it('returns true for data: URLs', () => {
    expect(isRestrictedPage('data:text/html,hello')).toBe(true);
  });

  it('returns true for chrome-extension: URLs', () => {
    expect(isRestrictedPage('chrome-extension://abc/popup.html')).toBe(true);
  });

  it('returns true for null/undefined', () => {
    expect(isRestrictedPage(null)).toBe(true);
    expect(isRestrictedPage(undefined)).toBe(true);
  });

  it('returns true for empty string', () => {
    expect(isRestrictedPage('')).toBe(true);
  });

  it('returns false for http URLs', () => {
    expect(isRestrictedPage('https://example.com')).toBe(false);
    expect(isRestrictedPage('http://example.com')).toBe(false);
  });
});

describe('pickDefaultTab', () => {
  it('returns null when no token', () => {
    expect(pickDefaultTab({ url: 'https://example.com', hasToken: false })).toBeNull();
  });

  it('returns "search" for restricted URLs', () => {
    expect(pickDefaultTab({ url: 'chrome://newtab/', hasToken: true })).toBe('search');
    expect(pickDefaultTab({ url: 'chrome://settings/', hasToken: true })).toBe('search');
    expect(pickDefaultTab({ url: 'about:blank', hasToken: true })).toBe('search');
    expect(pickDefaultTab({ url: undefined, hasToken: true })).toBe('search');
    expect(pickDefaultTab({ url: 'view-source:https://example.com', hasToken: true })).toBe('search');
    expect(pickDefaultTab({ url: 'data:text/html,hi', hasToken: true })).toBe('search');
  });

  it('returns "save" for regular http(s) URLs', () => {
    expect(pickDefaultTab({ url: 'https://example.com', hasToken: true })).toBe('save');
    expect(pickDefaultTab({ url: 'http://example.com', hasToken: true })).toBe('save');
  });
});

describe('setPopupMode', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
  });

  it('setup mode shows setup-view and hides header + panels', () => {
    setPopupMode('setup');
    expect(document.getElementById('setup-view').hidden).toBe(false);
    expect(document.getElementById('popup-header').hidden).toBe(true);
    expect(document.getElementById('save-view').hidden).toBe(true);
    expect(document.getElementById('search-view').hidden).toBe(true);
  });

  it('app mode hides setup-view and shows the header', () => {
    setPopupMode('setup');
    setPopupMode('app');
    expect(document.getElementById('setup-view').hidden).toBe(true);
    expect(document.getElementById('popup-header').hidden).toBe(false);
  });
});

describe('activateTab', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    setPopupMode('app');
  });

  it('activating "save" shows save panel, hides search panel, flips aria-selected', () => {
    activateTab('save');
    expect(document.getElementById('save-view').hidden).toBe(false);
    expect(document.getElementById('search-view').hidden).toBe(true);
    expect(document.getElementById('tab-save').getAttribute('aria-selected')).toBe('true');
    expect(document.getElementById('tab-search').getAttribute('aria-selected')).toBe('false');
  });

  it('activating "search" swaps which panel is visible', () => {
    activateTab('save');
    activateTab('search');
    expect(document.getElementById('search-view').hidden).toBe(false);
    expect(document.getElementById('save-view').hidden).toBe(true);
    expect(document.getElementById('tab-search').getAttribute('aria-selected')).toBe('true');
    expect(document.getElementById('tab-save').getAttribute('aria-selected')).toBe('false');
  });

  it('roving tabindex: active tab has tabindex 0, inactive has -1', () => {
    activateTab('save');
    expect(document.getElementById('tab-save').tabIndex).toBe(0);
    expect(document.getElementById('tab-search').tabIndex).toBe(-1);

    activateTab('search');
    expect(document.getElementById('tab-save').tabIndex).toBe(-1);
    expect(document.getElementById('tab-search').tabIndex).toBe(0);
  });

  it('does nothing when target tab is disabled', () => {
    activateTab('search');
    setTabEnabled('save', false, "can't save here");
    activateTab('save');
    expect(document.getElementById('search-view').hidden).toBe(false);
    expect(document.getElementById('tab-search').getAttribute('aria-selected')).toBe('true');
  });
});

describe('setTabEnabled', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    setPopupMode('app');
  });

  it('disabling sets aria-disabled, tabindex=-1, title, aria-label, and adds class', () => {
    setTabEnabled('save', false, 'reason text');
    const tab = document.getElementById('tab-save');
    expect(tab.getAttribute('aria-disabled')).toBe('true');
    expect(tab.tabIndex).toBe(-1);
    expect(tab.title).toBe('reason text');
    expect(tab.getAttribute('aria-label')).toBe('reason text');
    expect(tab.classList.contains('tab-disabled')).toBe(true);
  });

  it('enabling clears aria-disabled, title, aria-label, and the class', () => {
    setTabEnabled('save', false, 'reason');
    setTabEnabled('save', true);
    const tab = document.getElementById('tab-save');
    expect(tab.hasAttribute('aria-disabled')).toBe(false);
    expect(tab.title).toBe('');
    expect(tab.hasAttribute('aria-label')).toBe(false);
    expect(tab.classList.contains('tab-disabled')).toBe(false);
  });

  it('enabling without a prior disable is a no-op and does not throw', () => {
    expect(() => setTabEnabled('save', true)).not.toThrow();
    expect(document.getElementById('tab-save').hasAttribute('aria-disabled')).toBe(false);
  });
});

describe('isValidLimits', () => {
  it('returns true for valid limits object', () => {
    expect(isValidLimits(VALID_LIMITS)).toBe(true);
  });

  it('returns false for null/undefined', () => {
    expect(isValidLimits(null)).toBeFalsy();
    expect(isValidLimits(undefined)).toBeFalsy();
  });

  it('returns false when fields are missing', () => {
    expect(isValidLimits({ max_title_length: 100 })).toBe(false);
    expect(isValidLimits({ max_title_length: 100, max_description_length: 1000 })).toBe(false);
  });

  it('returns false for zero values', () => {
    expect(isValidLimits({ ...VALID_LIMITS, max_title_length: 0 })).toBe(false);
  });

  it('returns false for negative values', () => {
    expect(isValidLimits({ ...VALID_LIMITS, max_description_length: -1 })).toBe(false);
  });

  it('returns false for non-number types', () => {
    expect(isValidLimits({ ...VALID_LIMITS, max_title_length: '100' })).toBe(false);
    expect(isValidLimits({ ...VALID_LIMITS, max_bookmark_content_length: true })).toBe(false);
  });
});

describe('counterText', () => {
  it('formats small numbers', () => {
    expect(counterText(70, 100)).toBe('70 / 100');
  });

  it('uses toLocaleString for large numbers', () => {
    const text = counterText(1000, 5000);
    expect(text).toContain('1');
    expect(text).toContain('000');
    expect(text).toContain('5');
  });
});

// --- DOM-dependent tests ---

describe('truncateByCodePoints', () => {
  it('returns empty string for null/undefined/empty input', () => {
    expect(truncateByCodePoints(null, 10)).toBe('');
    expect(truncateByCodePoints(undefined, 10)).toBe('');
    expect(truncateByCodePoints('', 10)).toBe('');
  });

  it('passes under-limit input through unchanged', () => {
    expect(truncateByCodePoints('hello', 10)).toBe('hello');
  });

  it('passes input at exactly the limit through unchanged', () => {
    expect(truncateByCodePoints('a'.repeat(10), 10)).toBe('a'.repeat(10));
  });

  it('truncates limit + 1 input to exactly the limit', () => {
    expect(truncateByCodePoints('a'.repeat(11), 10)).toBe('a'.repeat(10));
  });

  it('preserves a surrogate pair at the boundary (does not split emoji)', () => {
    // 9 'a' + 🚀 = 10 code points but 11 UTF-16 units. Naive .substring(0, 10) would
    // drop the emoji's low surrogate. truncateByCodePoints sees length === max and
    // returns the string unchanged.
    const input = 'a'.repeat(9) + '🚀';
    const result = truncateByCodePoints(input, 10);
    expect(result).toBe(input);
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(result)).toBe(false);
  });

  it('drops the trailing emoji rather than splitting its surrogate pair', () => {
    // 10 'a' + 🚀 = 11 code points, max = 10. The slice keeps the first 10 code points
    // (10 'a'); the emoji is dropped whole. A naive .substring(0, 10) would also keep
    // 10 UTF-16 units, but in a different scenario could split — this test guards that
    // we slice on code-point indices, not UTF-16 indices.
    const result = truncateByCodePoints('a'.repeat(10) + '🚀', 10);
    expect(result).toBe('a'.repeat(10));
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(result)).toBe(false);
  });
});

describe('updateLimitFeedback', () => {
  let input, feedback;

  beforeEach(() => {
    input = document.createElement('input');
    feedback = document.createElement('span');
  });

  it('hides feedback below 70%', () => {
    input.value = 'a'.repeat(69);
    const result = updateLimitFeedback(input, feedback, 100);
    expect(feedback.style.visibility).toBe('hidden');
    expect(feedback.children.length).toBe(0);
    expect(feedback.style.color).toBe('');
    expect(result).toBe(false);
  });

  it('shows count at 70% with color set', () => {
    input.value = 'a'.repeat(70);
    const result = updateLimitFeedback(input, feedback, 100);
    expect(feedback.style.visibility).toBe('visible');
    expect(feedback.children.length).toBe(1);
    expect(feedback.children[0].textContent).toBe('70 / 100');
    expect(feedback.style.color).not.toBe('');
    expect(result).toBe(false);
  });

  it('shows count at 85% with different color than 70%', () => {
    input.value = 'a'.repeat(70);
    updateLimitFeedback(input, feedback, 100);
    const colorAt70 = feedback.style.color;

    input.value = 'a'.repeat(85);
    updateLimitFeedback(input, feedback, 100);
    const colorAt85 = feedback.style.color;

    expect(colorAt85).not.toBe(colorAt70);
    expect(feedback.children[0].textContent).toBe('85 / 100');
  });

  it('shows "Character limit reached" at exactly 100%', () => {
    input.value = 'a'.repeat(100);
    const result = updateLimitFeedback(input, feedback, 100);
    expect(feedback.style.visibility).toBe('visible');
    expect(feedback.children.length).toBe(2);
    expect(feedback.children[0].textContent).toBe('Character limit reached');
    expect(feedback.children[1].textContent).toBe('100 / 100');
    expect(result).toBe(false);
  });

  it('shows exceeded message above 100% and returns true', () => {
    input.value = 'a'.repeat(105);
    const result = updateLimitFeedback(input, feedback, 100);
    expect(feedback.style.visibility).toBe('visible');
    expect(feedback.children.length).toBe(2);
    expect(feedback.children[0].textContent).toBe('Character limit exceeded - saving is disabled');
    expect(feedback.children[1].textContent).toBe('105 / 100');
    expect(input.classList.contains('input-exceeded')).toBe(true);
    expect(result).toBe(true);
  });

  it('clears exceeded state when transitioning back below 70%', () => {
    input.value = 'a'.repeat(105);
    updateLimitFeedback(input, feedback, 100);
    expect(input.classList.contains('input-exceeded')).toBe(true);

    input.value = 'a'.repeat(50);
    updateLimitFeedback(input, feedback, 100);
    expect(input.classList.contains('input-exceeded')).toBe(false);
    expect(feedback.style.visibility).toBe('hidden');
    expect(feedback.children.length).toBe(0);
    expect(feedback.style.color).toBe('');
  });

  it('uses dark mode colors when prefers-color-scheme is dark', () => {
    window.matchMedia = vi.fn(() => ({ matches: true }));

    input.value = 'a'.repeat(85);
    updateLimitFeedback(input, feedback, 100);
    const darkColor = feedback.style.color;

    window.matchMedia = vi.fn(() => ({ matches: false }));
    updateLimitFeedback(input, feedback, 100);
    const lightColor = feedback.style.color;

    expect(darkColor).not.toBe(lightColor);
  });
});

describe('applyLimits', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('does not set maxLength on inputs', () => {
    const titleInput = document.getElementById('title');
    const descInput = document.getElementById('description');
    const titleMaxBefore = titleInput.maxLength;
    const descMaxBefore = descInput.maxLength;
    applyLimits(VALID_LIMITS);
    expect(titleInput.maxLength).toBe(titleMaxBefore);
    expect(descInput.maxLength).toBe(descMaxBefore);
  });
});

// --- Integration tests ---

describe('initSaveForm — fresh fetch (no cache)', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('fetches limits, tags, and page data; populates form fields; shows form', async () => {
    const tab = makeTab();
    mockPageData({ title: 'My Page', description: 'A description', content: 'Body text' });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('url').value).toBe('https://example.com');
    expect(document.getElementById('title').value).toBe('My Page');
    expect(document.getElementById('description').value).toBe('A description');
    expect(document.getElementById('save-form').hidden).toBe(false);
    expect(document.getElementById('loading-indicator').hidden).toBe(true);
  });

  it('truncates over-limit scraped title to max_title_length code points', async () => {
    const tab = makeTab();
    mockPageData({ title: 'a'.repeat(VALID_LIMITS.max_title_length + 50) });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(Array.from(document.getElementById('title').value).length).toBe(VALID_LIMITS.max_title_length);
  });

  it('truncates over-limit scraped description to max_description_length code points', async () => {
    const tab = makeTab();
    mockPageData({ description: 'b'.repeat(VALID_LIMITS.max_description_length + 50) });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(Array.from(document.getElementById('description').value).length).toBe(VALID_LIMITS.max_description_length);
  });

  // Regression guard for the keyboard-only flow: if Save ever ends up disabled
  // after truncating scraped values, auto-focus on Save would land on a disabled button
  // and Enter would do nothing.
  it('keeps Save enabled after truncating over-limit scraped values', async () => {
    const tab = makeTab();
    mockPageData({
      title: 'a'.repeat(VALID_LIMITS.max_title_length + 50),
      description: 'b'.repeat(VALID_LIMITS.max_description_length + 50),
    });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('save-btn').disabled).toBe(false);
  });

  it('passes under-limit scraped values through unchanged (no spurious slicing)', async () => {
    const tab = makeTab();
    const title = 'Short title';
    const description = 'A short description.';
    mockPageData({ title, description });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('title').value).toBe(title);
    expect(document.getElementById('description').value).toBe(description);
  });

  it('does not truncate a scraped title at exactly max_title_length', async () => {
    const tab = makeTab();
    const title = 'a'.repeat(VALID_LIMITS.max_title_length);
    mockPageData({ title });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('title').value).toBe(title);
  });

  it('does not truncate a scraped description at exactly max_description_length', async () => {
    const tab = makeTab();
    const description = 'b'.repeat(VALID_LIMITS.max_description_length);
    mockPageData({ description });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('description').value).toBe(description);
  });

  it('truncates a scraped title at exactly limit + 1 to exactly the limit', async () => {
    const tab = makeTab();
    mockPageData({ title: 'a'.repeat(VALID_LIMITS.max_title_length + 1) });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(Array.from(document.getElementById('title').value).length).toBe(VALID_LIMITS.max_title_length);
  });

  it('truncates a scraped description at exactly limit + 1 to exactly the limit', async () => {
    const tab = makeTab();
    mockPageData({ description: 'b'.repeat(VALID_LIMITS.max_description_length + 1) });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(Array.from(document.getElementById('description').value).length).toBe(VALID_LIMITS.max_description_length);
  });

  // Surrogate-pair safety: 99 'a' + 🚀 has UTF-16 length 101 but 100 code points
  // (= max_title_length). A naive `.substring(0, max_title_length)` would slice off
  // the emoji's low surrogate, leaving an unpaired high surrogate that Postgres rejects
  // with a 422. This test catches regressions back to UTF-16-based truncation.
  // Also asserts Save stays enabled and the counter shows "reached" (not "exceeded") —
  // the validator must agree with the truncation unit (code points, not UTF-16 units),
  // otherwise truncation succeeds but the validator falsely flags the value as exceeded.
  it('does not split surrogate pairs when the boundary lands on emoji and keeps Save enabled', async () => {
    const tab = makeTab();
    mockPageData({ title: 'a'.repeat(VALID_LIMITS.max_title_length - 1) + '🚀' });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const value = document.getElementById('title').value;
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(value)).toBe(false);
    expect(document.getElementById('save-btn').disabled).toBe(false);
    const titleFeedback = document.getElementById('title-limit');
    expect(titleFeedback.children[0].textContent).toBe('Character limit reached');
  });

  it('still disables Save when the user types over the limit after init', async () => {
    const tab = makeTab();
    mockPageData({ title: 'Short' });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const titleInput = document.getElementById('title');
    titleInput.value = 'x'.repeat(VALID_LIMITS.max_title_length + 1);
    titleInput.dispatchEvent(new Event('input'));

    expect(document.getElementById('save-btn').disabled).toBe(true);
  });

  it('writes immutable cache when both limits and tags succeed', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const setCall = chrome.storage.local.set.mock.calls.find(
      call => DRAFT_IMMUTABLE_KEY in call[0]
    );
    expect(setCall).toBeTruthy();
    const cached = setCall[0][DRAFT_IMMUTABLE_KEY];
    expect(cached.url).toBe('https://example.com');
    expect(cached.allTags).toEqual(VALID_TAGS);
    expect(cached.limits).toEqual(VALID_LIMITS);
  });

  it('does NOT write immutable cache when tags fail', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: { success: false, status: 500 },
    });

    await initSaveForm(tab);

    const setCall = chrome.storage.local.set.mock.calls.find(
      call => DRAFT_IMMUTABLE_KEY in call[0]
    );
    expect(setCall).toBeUndefined();
    // Form still renders
    expect(document.getElementById('save-form').hidden).toBe(false);
  });

  it('calls saveDraft() to persist mutable form fields', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const draftCall = chrome.storage.local.set.mock.calls.find(
      call => DRAFT_KEY in call[0]
    );
    expect(draftCall).toBeTruthy();
    expect(draftCall[0][DRAFT_KEY].url).toBe('https://example.com');
  });

  it('shows limit feedback if pre-populated values are at the limit', async () => {
    const tab = makeTab();
    mockPageData({ title: 'a'.repeat(100) });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const titleFeedback = document.getElementById('title-limit');
    expect(titleFeedback.style.visibility).toBe('visible');
    expect(titleFeedback.children[0].textContent).toBe('Character limit reached');
    expect(titleFeedback.children[1].textContent).toBe('100 / 100');
  });

  it('shows description limit feedback if pre-populated description is at the limit', async () => {
    const tab = makeTab();
    mockPageData({ description: 'b'.repeat(1000) });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const descFeedback = document.getElementById('description-limit');
    expect(descFeedback.style.visibility).toBe('visible');
    expect(descFeedback.children[0].textContent).toBe('Character limit reached');
    expect(descFeedback.children[1].textContent).toBe('1,000 / 1,000');
  });

  it('URL comes from tab.url, not from content script', async () => {
    const tab = makeTab('https://example.com/page#hash');
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('url').value).toBe('https://example.com/page#hash');
  });

  // Focus lands on the Save button after the form reveals so the user can press
  // Enter to save without reaching for the mouse. The manual Chrome smoke test gate
  // is the real proof — jsdom does not simulate Chrome's popup-paint focus race.
  it('focuses the Save button after the form reveals', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.activeElement).toBe(document.getElementById('save-btn'));
  });
});

describe('initSaveForm — cache hit', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('restores form from draft + immutable cache when URL matches', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'Edited Title', description: 'Edited desc', tags: ['tag1'] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'cached content', allTags: ['tag1', 'tag2'], limits: VALID_LIMITS },
    });

    await initSaveForm(tab);

    expect(document.getElementById('title').value).toBe('Edited Title');
    expect(document.getElementById('description').value).toBe('Edited desc');
    expect(document.getElementById('save-form').hidden).toBe(false);
  });

  it('skips GET_TAGS, GET_LIMITS, and getPageData when cache is valid', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'T', description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });

    await initSaveForm(tab);

    expect(chrome.runtime.sendMessage).not.toHaveBeenCalled();
    expect(chrome.scripting.executeScript).not.toHaveBeenCalled();
  });

  // Guards two real-world scenarios:
  //   1. Intentional user-typed over-limit drafts (existing "warn at >100%, disable Save" UX preserved).
  //   2. Legacy cached drafts produced by 0.3.0 versions that wrote untrimmed
  //      scraped values into DRAFT_KEY. Truncating on cache restore would silently alter
  //      user state. Both will exist in real-world installs after 0.4.0 ships.
  it('does not truncate over-limit values restored from cache', async () => {
    const tab = makeTab();
    const overLimitTitle = 'a'.repeat(VALID_LIMITS.max_title_length + 50);
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: overLimitTitle, description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });

    await initSaveForm(tab);

    expect(document.getElementById('title').value.length).toBe(VALID_LIMITS.max_title_length + 50);
  });

  it('applies cached limits without setting maxLength', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'T', description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: '', allTags: ['a'], limits: VALID_LIMITS },
    });

    const titleInput = document.getElementById('title');
    const maxBefore = titleInput.maxLength;

    await initSaveForm(tab);

    expect(titleInput.maxLength).toBe(maxBefore);
    expect(document.getElementById('save-form').hidden).toBe(false);
  });

  // Focus lands on the Save button on the cache-hit path too. Both paths share
  // the same form-reveal site, but a separate test guards against future refactors
  // that diverge them.
  it('focuses the Save button after restoring from cache', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'Edited Title', description: 'Edited desc', tags: ['tag1'] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'cached content', allTags: ['tag1', 'tag2'], limits: VALID_LIMITS },
    });

    await initSaveForm(tab);

    expect(document.activeElement).toBe(document.getElementById('save-btn'));
  });

  // Cached over-limit drafts (an accepted trade-off — both
  // legacy 0.3.0 untrimmed scrapes and intentional user-typed over-limit content)
  // disable the Save button, so focusing it would land on a no-op control. Route
  // focus to the offending field so editing it down re-enables Save naturally.
  it('focuses the offending field when restoring an over-limit cached title', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: {
        url: 'https://example.com',
        title: 'a'.repeat(VALID_LIMITS.max_title_length + 50),
        description: 'D',
        tags: [],
      },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });

    await initSaveForm(tab);

    expect(document.getElementById('save-btn').disabled).toBe(true);
    expect(document.activeElement).toBe(document.getElementById('title'));
  });

  it('focuses the description when only the description is over-limit in cache', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: {
        url: 'https://example.com',
        title: 'T',
        description: 'b'.repeat(VALID_LIMITS.max_description_length + 50),
        tags: [],
      },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });

    await initSaveForm(tab);

    expect(document.getElementById('save-btn').disabled).toBe(true);
    expect(document.activeElement).toBe(document.getElementById('description'));
  });

  // Opt-out: arrow-key tablist navigation passes { focus: false } through the
  // controller to preserve focus on the tab button (WAI-ARIA roving-tabindex).
  it('does not focus the Save button when called with { focus: false }', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'T', description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: 'c', allTags: ['a'], limits: VALID_LIMITS },
    });

    // Park focus somewhere predictable before init.
    const searchInput = document.getElementById('search-input');
    searchInput.focus();

    await initSaveForm(tab, { focus: false });

    expect(document.activeElement).not.toBe(document.getElementById('save-btn'));
  });
});

describe('initSaveForm — cache miss', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('fetches fresh data when draft URL does not match tab.url', async () => {
    const tab = makeTab('https://other.com');
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'T', description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: '', allTags: ['a'], limits: VALID_LIMITS },
    });
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(chrome.runtime.sendMessage).toHaveBeenCalled();
    expect(document.getElementById('url').value).toBe('https://other.com');
  });

  it('fetches fresh data when immutable cache has invalid limits', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'T', description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: '', allTags: ['a'], limits: { max_title_length: 0 } },
    });
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(chrome.runtime.sendMessage).toHaveBeenCalled();
  });

  it('fetches fresh data when immutable cache has non-array allTags', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'T', description: 'D', tags: [] },
      [DRAFT_IMMUTABLE_KEY]: { url: 'https://example.com', pageContent: '', allTags: 'not-an-array', limits: VALID_LIMITS },
    });
    mockPageData();
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(chrome.runtime.sendMessage).toHaveBeenCalled();
  });

  it('fetches fresh data when DRAFT_KEY exists but DRAFT_IMMUTABLE_KEY is missing', async () => {
    const tab = makeTab();
    chrome.storage.local.set({
      [DRAFT_KEY]: { url: 'https://example.com', title: 'User Edited', description: 'User Desc', tags: ['my-tag'] },
    });
    mockPageData({ title: 'Scraped Title' });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    // Fresh fetch replaces draft data — user edits are not preserved
    expect(chrome.runtime.sendMessage).toHaveBeenCalled();
    expect(document.getElementById('title').value).toBe('Scraped Title');
  });
});

describe('initSaveForm — error handling', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('names the rejected token with settings link on a PAT 401 from GET_LIMITS', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: { success: false, status: 401, authMode: 'pat' },
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const status = document.getElementById('save-status');
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain('access token was rejected');
    expect(status.querySelector('a').textContent).toBe('Update in settings');
  });

  it('routes an authRequired limits failure to the signed-out copy, not the generic error', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: { success: false, error: 'Not signed in', authRequired: true },
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const status = document.getElementById('save-status');
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain('signed out');
    expect(status.textContent).not.toContain("Can't load account limits");
  });

  it('shows "Can\'t load account limits" on network failure', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: null,
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const status = document.getElementById('save-status');
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain("Can't load account limits");
  });

  it('shows "Can\'t load account limits" on malformed limits response', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: { success: true, data: { max_title_length: 'bad' } },
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    const status = document.getElementById('save-status');
    expect(status.textContent).toContain("Can't load account limits");
  });

  it('hides loading indicator and keeps form hidden on error', async () => {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: { success: false, status: 500 },
      GET_TAGS: validTagsResponse(),
    });

    await initSaveForm(tab);

    expect(document.getElementById('loading-indicator').hidden).toBe(true);
    expect(document.getElementById('save-form').hidden).toBe(true);
  });
});

describe('handleSave', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  async function setupFormWithLimits(limitsOverrides = {}) {
    const tab = makeTab();
    mockPageData();
    mockMessages({
      GET_LIMITS: { success: true, data: { ...VALID_LIMITS, ...limitsOverrides } },
      GET_TAGS: validTagsResponse(),
    });
    await initSaveForm(tab);
    // Reset sendMessage for save assertions
    chrome.runtime.sendMessage.mockReset();
  }

  it('sends title/description without truncation', async () => {
    await setupFormWithLimits();
    document.getElementById('title').value = 'Test Title';
    document.getElementById('description').value = 'Test Description';
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    const sentBookmark = chrome.runtime.sendMessage.mock.calls[0][0].bookmark;
    expect(sentBookmark.title).toBe('Test Title');
    expect(sentBookmark.description).toBe('Test Description');
  });

  it('truncates content using limits.max_bookmark_content_length', async () => {
    await setupFormWithLimits({ max_bookmark_content_length: 5 });
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    const sentBookmark = chrome.runtime.sendMessage.mock.calls[0][0].bookmark;
    expect(Array.from(sentBookmark.content).length).toBeLessThanOrEqual(5);
  });

  // Page-body text from sites like Reddit/X.com routinely contains emoji. Two layers
  // of truncation apply (applyLimits during init, then the save handler at submit);
  // both must use code-point-aware truncation so neither produces an unpaired surrogate
  // that Postgres rejects with a 422.
  it('does not produce unpaired surrogates in sent content when emoji lands on the boundary', async () => {
    const tab = makeTab();
    // 9 'a' + 🚀 = 10 code points, 11 UTF-16 units. Limit is 10 code points, so the
    // emoji must be preserved whole.
    mockPageData({ content: 'a'.repeat(9) + '🚀' });
    mockMessages({
      GET_LIMITS: { success: true, data: { ...VALID_LIMITS, max_bookmark_content_length: 10 } },
      GET_TAGS: validTagsResponse(),
    });
    await initSaveForm(tab);
    chrome.runtime.sendMessage.mockReset();
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    const sentContent = chrome.runtime.sendMessage.mock.calls[0][0].bookmark.content;
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(sentContent)).toBe(false);
    expect(Array.from(sentContent).length).toBeLessThanOrEqual(10);
  });

  it('drops trailing emoji from content when boundary lands inside it rather than splitting the surrogate pair', async () => {
    const tab = makeTab();
    // 10 'a' + 🚀 = 11 code points, limit 10 → keep first 10 'a', drop the emoji.
    mockPageData({ content: 'a'.repeat(10) + '🚀' });
    mockMessages({
      GET_LIMITS: { success: true, data: { ...VALID_LIMITS, max_bookmark_content_length: 10 } },
      GET_TAGS: validTagsResponse(),
    });
    await initSaveForm(tab);
    chrome.runtime.sendMessage.mockReset();
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    const sentContent = chrome.runtime.sendMessage.mock.calls[0][0].bookmark.content;
    expect(sentContent).toBe('a'.repeat(10));
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(sentContent)).toBe(false);
  });

  it('passes under-limit content through unchanged', async () => {
    const tab = makeTab();
    const content = 'short body 🚀';
    mockPageData({ content });
    mockMessages({
      GET_LIMITS: validLimitsResponse(),
      GET_TAGS: validTagsResponse(),
    });
    await initSaveForm(tab);
    chrome.runtime.sendMessage.mockReset();
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    expect(chrome.runtime.sendMessage.mock.calls[0][0].bookmark.content).toBe(content);
  });

  it('shows error if limits is null', async () => {
    resetState();
    setupPopupDOM();
    // Don't set up limits — they remain null

    await handleSave(new Event('submit', { cancelable: true }));

    const status = document.getElementById('save-status');
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain("Can't load account limits");
  });

  it('calls clearDraft() on successful save', async () => {
    await setupFormWithLimits();
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    expect(chrome.storage.local.remove).toHaveBeenCalledWith([DRAFT_KEY, DRAFT_IMMUTABLE_KEY]);
  });

  it('sends correct bookmark payload via CREATE_BOOKMARK message', async () => {
    await setupFormWithLimits();
    document.getElementById('title').value = 'Test Title';
    document.getElementById('description').value = 'Test Desc';
    chrome.runtime.sendMessage.mockResolvedValue({ success: true });

    await handleSave(new Event('submit', { cancelable: true }));

    const msg = chrome.runtime.sendMessage.mock.calls[0][0];
    expect(msg.type).toBe('CREATE_BOOKMARK');
    expect(msg.bookmark.url).toBe('https://example.com');
    expect(msg.bookmark.title).toBe('Test Title');
    expect(msg.bookmark.description).toBe('Test Desc');
    expect(msg.bookmark.tags).toEqual(expect.any(Array));
  });
});

describe('handleSaveError', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
  });

  function getStatusText() {
    return document.getElementById('save-status').textContent;
  }

  function getStatusLink() {
    return document.getElementById('save-status').querySelector('a');
  }

  it('400 with detail array: joins messages', () => {
    handleSaveError({ status: 400, body: { detail: [{ msg: 'Field A invalid' }, { msg: 'Field B required' }] } });
    expect(getStatusText()).toContain('Field A invalid; Field B required');
  });

  it('422 with string detail: shows the string', () => {
    handleSaveError({ status: 422, body: { detail: 'URL is not valid' } });
    expect(getStatusText()).toContain('URL is not valid');
  });

  it('400 with no detail: shows "Invalid bookmark data"', () => {
    handleSaveError({ status: 400, body: {} });
    expect(getStatusText()).toContain('Invalid bookmark data');
  });

  it('401 on the PAT path: names the token with settings link', () => {
    handleSaveError({ status: 401, authMode: 'pat' });
    expect(getStatusText()).toContain('access token was rejected');
    expect(getStatusLink().textContent).toBe('Update in settings');
  });

  it('401 on the session path: names the session and points at tiddly.me', () => {
    handleSaveError({ status: 401, authMode: 'clerk' });
    expect(getStatusText()).toContain('session was rejected');
    expect(getStatusLink().textContent).toBe('Open Tiddly');
  });

  it('authRequired failure (signed out mid-open, e.g. after a stale snapshot render): signed-out copy, routed on the flag not the prose', () => {
    handleSaveError({ error: 'some future rewording of the auth error', authRequired: true });
    expect(getStatusText()).toContain('signed out');
    expect(getStatusLink().textContent).toBe('Open settings');
  });

  it('401 with the account_deleted terminal code: renders the backend detail, no misleading remedy link', () => {
    handleSaveError({
      status: 401,
      authMode: 'clerk',
      body: { detail: 'This account was deleted', error_code: 'account_deleted' },
    });
    expect(getStatusText()).toContain('This account was deleted');
    expect(getStatusLink()).toBeNull();
  });

  it('402 with resource and limit: shows structured message with pricing link', () => {
    handleSaveError({ status: 402, body: { error_code: 'QUOTA_EXCEEDED', resource: 'bookmark', limit: 10, current: 10 } });
    expect(getStatusText()).toContain('limit of 10 bookmarks');
    expect(getStatusLink().textContent).toBe('Manage your plan');
    expect(getStatusLink().href).toContain('/pricing');
  });

  it('402 with no structured fields: falls back to generic message', () => {
    handleSaveError({ status: 402, body: {} });
    expect(getStatusText()).toContain('Bookmark limit reached.');
  });

  it('409 with ARCHIVED_URL_EXISTS: shows archived message with link', () => {
    handleSaveError({ status: 409, body: { error_code: 'ARCHIVED_URL_EXISTS', existing_bookmark_id: 'abc-123' } });
    expect(getStatusText()).toContain('This bookmark is archived.');
    const link = getStatusLink();
    expect(link.textContent).toBe('View it');
    expect(link.href).toContain('abc-123');
  });

  it('409 without ARCHIVED_URL_EXISTS: shows "Already saved"', () => {
    handleSaveError({ status: 409, body: {} });
    expect(getStatusText()).toContain('Already saved');
  });

  it('429: shows rate limit message with retry seconds and pricing link', () => {
    handleSaveError({ status: 429, retryAfter: 30 });
    expect(getStatusText()).toContain('Rate limited');
    expect(getStatusText()).toContain('30');
    expect(getStatusLink().textContent).toBe('Higher limits available');
    expect(getStatusLink().href).toContain('/pricing');
  });

  it('451: shows "Accept terms first." with link', () => {
    handleSaveError({ status: 451 });
    expect(getStatusText()).toContain('Accept terms first.');
    expect(getStatusLink().textContent).toBe('Open Tiddly');
  });

  it('unknown status: shows response.error or fallback', () => {
    handleSaveError({ status: 503, error: 'Service unavailable' });
    expect(getStatusText()).toContain('Service unavailable');
  });

  it('no status: shows "Unexpected error (network)"', () => {
    handleSaveError({ error: null });
    expect(getStatusText()).toContain('Unexpected error (network)');
  });
});

describe('updateSaveButtonState', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  async function setupWithLimits(limitsOverrides = {}) {
    const tab = makeTab();
    mockPageData({ title: 'Short', description: 'Short' });
    mockMessages({
      GET_LIMITS: { success: true, data: { ...VALID_LIMITS, ...limitsOverrides } },
      GET_TAGS: validTagsResponse(),
    });
    await initSaveForm(tab);
  }

  it('disables save when title exceeds limit', async () => {
    await setupWithLimits({ max_title_length: 10 });
    document.getElementById('title').value = 'a'.repeat(11);
    updateSaveButtonState();
    expect(document.getElementById('save-btn').disabled).toBe(true);
  });

  it('disables save when description exceeds limit', async () => {
    await setupWithLimits({ max_description_length: 10 });
    document.getElementById('description').value = 'a'.repeat(11);
    updateSaveButtonState();
    expect(document.getElementById('save-btn').disabled).toBe(true);
  });

  it('re-enables save when both fields are within limits', async () => {
    await setupWithLimits({ max_title_length: 10 });
    document.getElementById('title').value = 'a'.repeat(11);
    updateSaveButtonState();
    expect(document.getElementById('save-btn').disabled).toBe(true);

    document.getElementById('title').value = 'a'.repeat(5);
    updateSaveButtonState();
    expect(document.getElementById('save-btn').disabled).toBe(false);
  });

  it('does not throw when limits is null', () => {
    expect(() => updateSaveButtonState()).not.toThrow();
  });
});

describe('saveDraft / clearDraft', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('saveDraft writes DRAFT_KEY with url, title, description, tags', () => {
    document.getElementById('url').value = 'https://example.com';
    document.getElementById('title').value = 'My Title';
    document.getElementById('description').value = 'My Desc';

    saveDraft();

    const setCall = chrome.storage.local.set.mock.calls.find(call => DRAFT_KEY in call[0]);
    expect(setCall).toBeTruthy();
    const draft = setCall[0][DRAFT_KEY];
    expect(draft.url).toBe('https://example.com');
    expect(draft.title).toBe('My Title');
    expect(draft.description).toBe('My Desc');
    expect(draft.tags).toEqual([]);
  });

  it('clearDraft removes both DRAFT_KEY and DRAFT_IMMUTABLE_KEY', () => {
    clearDraft();

    expect(chrome.storage.local.remove).toHaveBeenCalledWith([DRAFT_KEY, DRAFT_IMMUTABLE_KEY]);
  });
});

// --- Search view tests ---

function searchResponse(items = [], has_more = false) {
  return { success: true, data: { items, has_more } };
}

describe('initSearchView', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('fetches tags and shows them in dropdown on focus', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    const tagInput = document.getElementById('search-tag-input');
    tagInput.dispatchEvent(new Event('focus'));

    const dropdown = document.getElementById('search-tag-dropdown');
    expect(dropdown.hidden).toBe(false);
    expect(dropdown.querySelectorAll('.search-tag-dropdown-item').length).toBe(VALID_TAGS.length);
  });

  // The search path renders only authFailureMessage().message (no link) —
  // covered here so a shape change to that helper can't silently break the
  // one consumer the save-path tests don't exercise.
  it('401 on the session path: search empty-state names the rejected session', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: { success: false, status: 401, authMode: 'clerk' },
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    const emptyState = document.querySelector('#search-results .empty-state');
    expect(emptyState.textContent).toContain('session was rejected');
  });

  it('401 with the account_deleted terminal code: search empty-state renders the backend detail', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: {
        success: false,
        status: 401,
        authMode: 'clerk',
        body: { detail: 'This account was deleted', error_code: 'account_deleted' },
      },
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    const emptyState = document.querySelector('#search-results .empty-state');
    expect(emptyState.textContent).toContain('This account was deleted');
  });

  it('filters tags by text input', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    const tagInput = document.getElementById('search-tag-input');
    tagInput.value = 'py';
    tagInput.dispatchEvent(new Event('input'));

    const dropdown = document.getElementById('search-tag-dropdown');
    const items = dropdown.querySelectorAll('.search-tag-dropdown-item');
    expect(items.length).toBe(1);
    expect(items[0].textContent).toBe('python');
  });

  it('still works if GET_TAGS fails', async () => {
    mockMessages({
      GET_TAGS: { success: false, status: 500 },
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    const tagInput = document.getElementById('search-tag-input');
    tagInput.dispatchEvent(new Event('focus'));

    const dropdown = document.getElementById('search-tag-dropdown');
    expect(dropdown.querySelectorAll('.search-tag-dropdown-item').length).toBe(0);
  });

  it('sends initial search with default sort_by=created_at and sort_order=desc', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();

    const searchCall = chrome.runtime.sendMessage.mock.calls.find(
      c => c[0].type === 'SEARCH_BOOKMARKS'
    );
    expect(searchCall).toBeTruthy();
    expect(searchCall[0].sort_by).toBe('created_at');
    expect(searchCall[0].sort_order).toBe('desc');
  });

  it('does not mutate panel visibility (panels are the controller\'s responsibility)', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    const searchView = document.getElementById('search-view');
    const saveView = document.getElementById('save-view');
    searchView.hidden = true;
    saveView.hidden = true;

    await initSearchView();

    expect(searchView.hidden).toBe(true);
    expect(saveView.hidden).toBe(true);
  });

  // Focus lands on the search input so the user can type immediately. The manual
  // Chrome smoke test gate is the real proof — jsdom does not simulate Chrome's
  // popup-paint focus race.
  // The focus call is the last synchronous statement of initSearchView; if a future
  // refactor inserts an `await` before it (e.g., to focus only after results render),
  // this assertion may need to flush more microtasks before checking activeElement.
  it('focuses the search input after initialization', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();

    expect(document.activeElement).toBe(document.getElementById('search-input'));
  });

  // Opt-out: arrow-key tablist navigation passes { focus: false } through the
  // controller to preserve focus on the tab button (WAI-ARIA roving-tabindex).
  it('does not focus the search input when called with { focus: false }', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    // Park focus somewhere predictable before init runs so we can prove init didn't
    // move it.
    const titleInput = document.getElementById('title');
    titleInput.focus();

    await initSearchView({ focus: false });

    expect(document.activeElement).not.toBe(document.getElementById('search-input'));
  });
});

describe('search tag filtering', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  function selectTagFromDropdown(tagName) {
    const tagInput = document.getElementById('search-tag-input');
    tagInput.dispatchEvent(new Event('focus'));
    const items = document.querySelectorAll('.search-tag-dropdown-item');
    const item = [...items].find(i => i.textContent === tagName);
    item.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  }

  it('selecting a tag adds a chip and triggers search with tags param', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });

    selectTagFromDropdown('python');
    await new Promise(r => setTimeout(r, 0));

    // Chip should appear
    const chips = document.getElementById('search-active-tags');
    expect(chips.children.length).toBe(1);
    expect(chips.children[0].textContent).toContain('python');

    // Input should be cleared
    expect(document.getElementById('search-tag-input').value).toBe('');

    // Search should include tags
    const searchCall = chrome.runtime.sendMessage.mock.calls.find(
      c => c[0].type === 'SEARCH_BOOKMARKS'
    );
    expect(searchCall[0].tags).toEqual(['python']);
  });

  it('selecting multiple tags passes all tags to search', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });
    selectTagFromDropdown('python');
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });
    selectTagFromDropdown('rust');
    await new Promise(r => setTimeout(r, 0));

    const searchCall = chrome.runtime.sendMessage.mock.calls.find(
      c => c[0].type === 'SEARCH_BOOKMARKS'
    );
    expect(searchCall[0].tags).toEqual(expect.arrayContaining(['python', 'rust']));
    expect(searchCall[0].tags.length).toBe(2);
  });

  it('selected tags are excluded from dropdown', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });
    selectTagFromDropdown('python');
    await new Promise(r => setTimeout(r, 0));

    // Open dropdown again — python should not appear
    const tagInput = document.getElementById('search-tag-input');
    tagInput.dispatchEvent(new Event('focus'));
    const items = document.querySelectorAll('.search-tag-dropdown-item');
    const itemTexts = [...items].map(i => i.textContent);
    expect(itemTexts).not.toContain('python');
    expect(items.length).toBe(VALID_TAGS.length - 1);
  });

  it('removing a tag chip removes it from filter and re-triggers search', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });
    selectTagFromDropdown('python');
    await new Promise(r => setTimeout(r, 0));

    // Remove the tag
    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });
    const removeBtn = document.querySelector('.search-active-tag .remove-tag');
    removeBtn.click();
    await new Promise(r => setTimeout(r, 0));

    // Chips should be empty
    expect(document.getElementById('search-active-tags').children.length).toBe(0);

    // Search should not have tags
    const searchCall = chrome.runtime.sendMessage.mock.calls.find(
      c => c[0].type === 'SEARCH_BOOKMARKS'
    );
    expect(searchCall[0].tags).toBeUndefined();
  });
});

describe('search sort', () => {
  beforeEach(() => {
    resetState();
    setupPopupDOM();
    resetChromeStorage();
  });

  it('changing sort triggers search with correct sort_by', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });

    const sortSelect = document.getElementById('search-sort-select');
    sortSelect.value = 'last_used_at';
    sortSelect.dispatchEvent(new Event('change'));
    await new Promise(r => setTimeout(r, 0));

    const searchCall = chrome.runtime.sendMessage.mock.calls.find(
      c => c[0].type === 'SEARCH_BOOKMARKS'
    );
    expect(searchCall[0].sort_by).toBe('last_used_at');
    expect(searchCall[0].sort_order).toBe('desc');
  });

  it('title sort uses asc order', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    chrome.runtime.sendMessage.mockReset();
    mockMessages({ SEARCH_BOOKMARKS: searchResponse() });

    const sortSelect = document.getElementById('search-sort-select');
    sortSelect.value = 'title';
    sortSelect.dispatchEvent(new Event('change'));
    await new Promise(r => setTimeout(r, 0));

    const searchCall = chrome.runtime.sendMessage.mock.calls.find(
      c => c[0].type === 'SEARCH_BOOKMARKS'
    );
    expect(searchCall[0].sort_by).toBe('title');
    expect(searchCall[0].sort_order).toBe('asc');
  });

  it('relevance option is always visible in sort dropdown', async () => {
    mockMessages({
      GET_TAGS: validTagsResponse(),
      SEARCH_BOOKMARKS: searchResponse(),
    });

    await initSearchView();
    await new Promise(r => setTimeout(r, 0));

    const sortSelect = document.getElementById('search-sort-select');
    const relevanceOption = sortSelect.querySelector('option[value="relevance"]');
    expect(relevanceOption).not.toBeNull();
    expect(relevanceOption.hidden).toBe(false);
  });
});
