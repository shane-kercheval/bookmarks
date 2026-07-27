// --- Constants ---

export const SCRAPE_CAP = 200000;
export const INITIAL_CHIPS_COUNT = 8;
export const DRAFT_KEY = 'draft';
export const DRAFT_IMMUTABLE_KEY = 'draftImmutable';

// Truncates by Unicode code point rather than UTF-16 code unit, so emoji
// at the boundary aren't split into unpaired surrogates (which Postgres rejects).
// Grapheme clusters (flag emoji, ZWJ family sequences) may render with a missing
// component if truncated mid-cluster — accepted trade-off; escalate to Intl.Segmenter
// only if real users complain.
export function truncateByCodePoints(str, max) {
  const s = str || '';
  const codePoints = Array.from(s);
  return codePoints.length <= max ? s : codePoints.slice(0, max).join('');
}

// --- DOM refs (set via setupDOM) ---

let loadingView, setupView, saveView, searchView;
let popupHeader, tabSave, tabSearch, settingsBtn;
let saveForm, loadingIndicator, urlInput, titleInput, descriptionInput;
let titleLimit, descriptionLimit;
let tagsInput, tagChipsContainer, tagSuggestions, saveBtn, saveStatus, clearTagsBtn;
let searchInput, searchResults, searchLoading, loadMoreBtn;
let searchTagInput, searchTagDropdown, searchSortSelect, searchActiveTags;

// --- Mutable state ---

let pageContent = '';
let allTags = [];
let selectedTags = new Set();
let defaultTagSet = new Set();
let showingAllTags = false;
let limits = null;
let flashTimerId = null;
let saving = false;
let searchOffset = 0;
let searchDebounceTimer = null;
let searchRequestId = 0;
let searchFilterTags = new Set();
let searchSort = 'created_at';
let searchAvailableTags = [];

// --- Setup / Reset ---

export function setupDOM(elements) {
  loadingView = elements.loadingView;
  setupView = elements.setupView;
  saveView = elements.saveView;
  searchView = elements.searchView;
  popupHeader = elements.popupHeader;
  tabSave = elements.tabSave;
  tabSearch = elements.tabSearch;
  settingsBtn = elements.settingsBtn;
  saveForm = elements.saveForm;
  loadingIndicator = elements.loadingIndicator;
  urlInput = elements.urlInput;
  titleInput = elements.titleInput;
  descriptionInput = elements.descriptionInput;
  titleLimit = elements.titleLimit;
  descriptionLimit = elements.descriptionLimit;
  tagsInput = elements.tagsInput;
  tagChipsContainer = elements.tagChipsContainer;
  tagSuggestions = elements.tagSuggestions;
  saveBtn = elements.saveBtn;
  saveStatus = elements.saveStatus;
  clearTagsBtn = elements.clearTagsBtn;
  searchInput = elements.searchInput;
  searchResults = elements.searchResults;
  searchLoading = elements.searchLoading;
  loadMoreBtn = elements.loadMoreBtn;
  searchTagInput = elements.searchTagInput;
  searchTagDropdown = elements.searchTagDropdown;
  searchSortSelect = elements.searchSortSelect;
  searchActiveTags = elements.searchActiveTags;
}

export function resetState() {
  pageContent = '';
  allTags = [];
  selectedTags = new Set();
  defaultTagSet = new Set();
  showingAllTags = false;
  limits = null;
  clearTimeout(flashTimerId);
  flashTimerId = null;
  saving = false;
  searchOffset = 0;
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = null;
  searchRequestId = 0;
  searchFilterTags = new Set();
  searchSort = 'created_at';
  searchAvailableTags = [];
  // Clear DOM refs
  setupView = null;
  saveView = null;
  searchView = null;
  popupHeader = null;
  tabSave = null;
  tabSearch = null;
  settingsBtn = null;
  saveForm = null;
  loadingIndicator = null;
  urlInput = null;
  titleInput = null;
  descriptionInput = null;
  titleLimit = null;
  descriptionLimit = null;
  tagsInput = null;
  tagChipsContainer = null;
  tagSuggestions = null;
  saveBtn = null;
  saveStatus = null;
  clearTagsBtn = null;
  searchInput = null;
  searchResults = null;
  searchLoading = null;
  loadMoreBtn = null;
  searchTagInput = null;
  searchTagDropdown = null;
  searchSortSelect = null;
  searchActiveTags = null;
}

// --- Pure helpers ---

export function isRestrictedPage(url) {
  return !url || /^(chrome|about|chrome-extension|devtools|edge|data|blob|view-source):/.test(url);
}

// Returns 'save' | 'search' for the tab to activate on popup open,
// or null when the popup should render the setup view instead.
export function pickDefaultTab({ url, hasToken }) {
  if (!hasToken) return null;
  return isRestrictedPage(url) ? 'search' : 'save';
}

export function counterText(current, max) {
  return `${current.toLocaleString()} / ${max.toLocaleString()}`;
}

function lerpColor(c1, c2, t) {
  t = Math.max(0, Math.min(1, t));
  return '#' + c1.map((v, i) =>
    Math.round(v + (c2[i] - v) * t).toString(16).padStart(2, '0')
  ).join('');
}

const COLORS = {
  gray:        [209, 213, 219],
  textLight:   [17, 24, 39],
  textDark:    [224, 224, 224],
  orangeLight: [217, 119, 6],
  orangeDark:  [251, 191, 36],
  redLight:    [220, 38, 38],
  redDark:     [252, 165, 165],
};

function getLimitColor(ratio) {
  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (ratio <= 0.85) {
    const t = (ratio - 0.7) / 0.15;
    return lerpColor(COLORS.gray, dark ? COLORS.textDark : COLORS.textLight, t);
  }
  const t = (ratio - 0.85) / 0.15;
  const from = dark ? COLORS.orangeDark : COLORS.orangeLight;
  const to = dark ? COLORS.redDark : COLORS.redLight;
  return lerpColor(from, to, Math.min(t, 1));
}

function setFeedbackContent(feedbackEl, { message, count }) {
  feedbackEl.replaceChildren();
  if (message) {
    const msg = document.createElement('span');
    msg.textContent = message;
    feedbackEl.appendChild(msg);
  }
  if (count) {
    const cnt = document.createElement('span');
    cnt.textContent = count;
    cnt.style.marginLeft = 'auto';
    feedbackEl.appendChild(cnt);
  }
}

export function isValidLimits(obj) {
  return obj
    && typeof obj.max_title_length === 'number' && obj.max_title_length > 0
    && typeof obj.max_description_length === 'number' && obj.max_description_length > 0
    && typeof obj.max_bookmark_content_length === 'number' && obj.max_bookmark_content_length > 0;
}

// --- DOM helpers ---

// Two orthogonal axes: setup vs app mode, and which content tab is active.
// setPopupMode gates the whole UI; activateTab switches panels within app mode.

export function setPopupMode(mode) {
  // The loading view is visible by default in the markup (the auth probe can
  // take seconds on a cold worker); resolving to either mode retires it.
  if (loadingView) loadingView.hidden = true;
  if (mode === 'setup') {
    setupView.hidden = false;
    popupHeader.hidden = true;
    saveView.hidden = true;
    searchView.hidden = true;
  } else {
    setupView.hidden = true;
    popupHeader.hidden = false;
  }
}

function tabElement(name) {
  return name === 'save' ? tabSave : tabSearch;
}

function panelElement(name) {
  return name === 'save' ? saveView : searchView;
}

export function activateTab(name) {
  const target = tabElement(name);
  if (target.getAttribute('aria-disabled') === 'true') return;

  for (const which of ['save', 'search']) {
    const tab = tabElement(which);
    const panel = panelElement(which);
    const isActive = which === name;
    tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    tab.tabIndex = isActive ? 0 : -1;
    panel.hidden = !isActive;
  }
}

export function setTabEnabled(name, enabled, reason) {
  const tab = tabElement(name);
  if (enabled) {
    tab.removeAttribute('aria-disabled');
    tab.removeAttribute('title');
    tab.removeAttribute('aria-label');
    tab.classList.remove('tab-disabled');
  } else {
    tab.setAttribute('aria-disabled', 'true');
    tab.tabIndex = -1;
    tab.classList.add('tab-disabled');
    if (reason) {
      tab.title = reason;
      tab.setAttribute('aria-label', reason);
    }
  }
}

export function updateLimitFeedback(input, feedbackEl, maxLength) {
  // Count by Unicode code points, not UTF-16 code units, so the validator agrees
  // with truncateByCodePoints. A title like 99 'a' + '🚀' is 100 code points but
  // 101 UTF-16 units; counting UTF-16 would falsely flag at-limit emoji titles
  // as exceeded and disable Save.
  const len = Array.from(input.value).length;
  const ratio = len / maxLength;
  const count = counterText(len, maxLength);

  input.classList.remove('input-exceeded');

  if (ratio < 0.7) {
    feedbackEl.style.visibility = 'hidden';
    feedbackEl.replaceChildren();
    feedbackEl.style.color = '';
    return false;
  }

  feedbackEl.style.visibility = 'visible';
  feedbackEl.style.color = getLimitColor(ratio);

  if (ratio > 1) {
    setFeedbackContent(feedbackEl, {
      message: 'Character limit exceeded - saving is disabled',
      count,
    });
    input.classList.add('input-exceeded');
    return true;
  }

  if (ratio >= 1) {
    setFeedbackContent(feedbackEl, {
      message: 'Character limit reached',
      count,
    });
    return false;
  }

  setFeedbackContent(feedbackEl, { count });
  return false;
}

export function updateSaveButtonState() {
  if (!limits || saving) return;
  const titleExceeded = updateLimitFeedback(titleInput, titleLimit, limits.max_title_length);
  const descExceeded = updateLimitFeedback(descriptionInput, descriptionLimit, limits.max_description_length);
  saveBtn.disabled = titleExceeded || descExceeded;
}

// 401 copy names the credential that was actually rejected (the request
// envelope's authMode) — "Invalid token" at a session-authed user, or a
// generic auth error at a deleted account, sends people to the wrong remedy.
// authRequired (structured flag, set by the worker when no credential existed
// at resolution time — e.g. signed out after a snapshot-rendered popup opened)
// gets the signed-out copy rather than a generic failure.
function authFailureMessage(response) {
  if (response?.authRequired) {
    return {
      message: "You're signed out — sign in at tiddly.me, or add an access token in settings.",
      link: { text: 'Open settings', onClick: () => chrome.runtime.openOptionsPage() },
    };
  }
  if (response?.body?.error_code === 'account_deleted') {
    return {
      message: response.body?.detail || 'This account was deleted.',
      link: null,
    };
  }
  if (response?.authMode === 'clerk') {
    return {
      message: 'Your session was rejected — sign in again at tiddly.me.',
      link: { text: 'Open Tiddly', href: 'https://tiddly.me' },
    };
  }
  return {
    message: 'Your access token was rejected.',
    link: { text: 'Update in settings', onClick: () => chrome.runtime.openOptionsPage() },
  };
}

export function showSaveStatus(message, type, link) {
  saveStatus.replaceChildren();
  saveStatus.appendChild(document.createTextNode(message));
  if (link) {
    const a = document.createElement('a');
    a.textContent = link.text;
    if (link.href) {
      a.href = link.href;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
    }
    if (link.onClick) {
      a.addEventListener('click', link.onClick);
    }
    saveStatus.appendChild(document.createTextNode(' '));
    saveStatus.appendChild(a);
  }
  saveStatus.className = `status ${type}`;
  saveStatus.hidden = false;
}

export function applyLimits(limitsObj) {
  limits = limitsObj;
  pageContent = truncateByCodePoints(pageContent, limitsObj.max_bookmark_content_length);
}

// --- Draft management ---

export function saveDraft() {
  chrome.storage.local.set({
    [DRAFT_KEY]: {
      url: urlInput.value,
      title: titleInput.value,
      description: descriptionInput.value,
      tags: [...selectedTags],
    }
  });
}

export function clearDraft() {
  chrome.storage.local.remove([DRAFT_KEY, DRAFT_IMMUTABLE_KEY]);
}

// --- Page data ---

export async function getPageData(tab) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      // The injected function runs in the page context and cannot capture closures
      // from this module, so the code-point truncation logic from truncateByCodePoints
      // is inlined here. Keep it in sync if the helper changes.
      func: (maxLen) => {
        const text = document.body.innerText || '';
        const codePoints = Array.from(text);
        const content = codePoints.length <= maxLen ? text : codePoints.slice(0, maxLen).join('');
        return {
          title: document.title,
          description: document.querySelector('meta[name="description"]')?.content
            || document.querySelector('meta[property="og:description"]')?.content
            || '',
          content
        };
      },
      args: [SCRAPE_CAP]
    });
    return result.result;
  } catch {
    return { title: tab.title || '', description: '', content: '' };
  }
}

// --- Save form ---

export async function initSaveForm(tab, { focus = true } = {}) {
  const storage = await chrome.storage.local.get([
    'defaultTags', 'lastUsedTags', DRAFT_KEY, DRAFT_IMMUTABLE_KEY
  ]);

  const draft = storage[DRAFT_KEY];
  const immutable = storage[DRAFT_IMMUTABLE_KEY];
  const hasCachedData = draft
    && immutable
    && draft.url === tab.url
    && immutable.url === tab.url
    && Array.isArray(immutable.allTags)
    && isValidLimits(immutable.limits);

  const defaultTags = storage.defaultTags || [];
  const lastUsedTags = storage.lastUsedTags || [];
  defaultTagSet = new Set(defaultTags);

  if (hasCachedData) {
    // Restore from cache — skip all API calls and page scraping
    urlInput.value = tab.url;
    titleInput.value = draft.title;
    descriptionInput.value = draft.description;
    pageContent = typeof immutable.pageContent === 'string' ? immutable.pageContent : '';
    allTags = immutable.allTags;
    (Array.isArray(draft.tags) ? draft.tags : []).forEach(t => selectedTags.add(t));
    applyLimits(immutable.limits);
  } else {
    // Fresh fetch — fire page scrape, GET_LIMITS, and GET_TAGS in parallel
    urlInput.value = tab.url;

    const [pageData, limitsResult, tagsResult] = await Promise.all([
      getPageData(tab),
      chrome.runtime.sendMessage({ type: 'GET_LIMITS' }).catch(() => null),
      chrome.runtime.sendMessage({ type: 'GET_TAGS' }).catch(() => null),
    ]);

    // Validate limits
    if (!limitsResult?.success || !isValidLimits(limitsResult.data)) {
      loadingIndicator.hidden = true;
      if (limitsResult?.status === 401 || limitsResult?.authRequired) {
        const { message, link } = authFailureMessage(limitsResult);
        showSaveStatus(message, 'error', link);
      } else {
        showSaveStatus("Can't load account limits", 'error');
      }
      return;
    }

    pageContent = pageData.content || '';
    applyLimits(limitsResult.data);

    titleInput.value = truncateByCodePoints(pageData.title, limitsResult.data.max_title_length);
    descriptionInput.value = truncateByCodePoints(pageData.description, limitsResult.data.max_description_length);

    let tagsSuccess = false;
    if (tagsResult?.success && Array.isArray(tagsResult.data?.tags)) {
      allTags = tagsResult.data.tags.map(t => t.name);
      tagsSuccess = true;
    }

    [...new Set([...defaultTags, ...lastUsedTags])].forEach(t => selectedTags.add(t));

    // Cache immutable data only if both limits and tags succeeded
    if (tagsSuccess) {
      chrome.storage.local.set({
        [DRAFT_IMMUTABLE_KEY]: {
          url: tab.url,
          pageContent,
          allTags,
          limits: limitsResult.data,
        }
      });
    }

    saveDraft();
  }

  renderTagChips();

  loadingIndicator.hidden = true;
  saveForm.hidden = false;

  titleInput.addEventListener('input', () => {
    saveDraft();
    updateSaveButtonState();
  });
  descriptionInput.addEventListener('input', () => {
    saveDraft();
    updateSaveButtonState();
  });

  updateSaveButtonState();

  // Keyboard-first contract: focus where the user needs to act. Save is the usual
  // target, but cache-hit can restore over-limit drafts that disable Save (an
  // accepted trade-off); in that state, route the user to the offending field
  // so editing it down re-enables Save and Tab+Enter completes the save.
  // The `focus` option is opt-out so callers like the arrow-key tablist handler
  // can preserve the WAI-ARIA roving-tabindex pattern (focus stays on the tab
  // button, user explicitly Tabs out of the tablist to enter the panel).
  if (focus) {
    if (saveBtn.disabled) {
      const firstExceeded =
        titleInput.classList.contains('input-exceeded') ? titleInput
        : descriptionInput.classList.contains('input-exceeded') ? descriptionInput
        : null;
      (firstExceeded || saveBtn).focus();
    } else {
      saveBtn.focus();
    }
  }

  tagsInput.addEventListener('input', () => {
    renderTagChips();
  });

  clearTagsBtn.addEventListener('click', () => {
    selectedTags = new Set(defaultTagSet);
    tagsInput.value = '';
    renderTagChips();
    saveDraft();
  });

  tagsInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const newTag = tagsInput.value.trim().toLowerCase().replace(/_/g, '-');
      if (newTag) {
        selectedTags.add(newTag);
        tagsInput.value = '';
        renderTagChips();
        saveDraft();
      }
    }
  });

  saveForm.addEventListener('submit', handleSave);
}

// --- Tag rendering ---

export function renderTagChips() {
  const filterText = tagsInput.value.trim().toLowerCase();
  tagChipsContainer.replaceChildren();
  tagSuggestions.replaceChildren();

  let visibleTags = allTags;
  if (filterText) {
    visibleTags = allTags.filter(t => t.includes(filterText));
  }

  const customSelected = [...selectedTags].filter(t => !allTags.includes(t));
  let tagsToShow;
  if (showingAllTags || filterText) {
    tagsToShow = [...visibleTags, ...customSelected.filter(t => !filterText || t.includes(filterText))];
  } else {
    const topTags = visibleTags.slice(0, INITIAL_CHIPS_COUNT);
    const selectedNotInTop = [...selectedTags].filter(
      t => !topTags.includes(t)
    );
    tagsToShow = [...topTags, ...selectedNotInTop];
  }

  tagsToShow.forEach(tag => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'tag-chip' + (selectedTags.has(tag) ? ' selected' : '');
    chip.textContent = tag;
    chip.addEventListener('click', () => {
      if (selectedTags.has(tag)) {
        selectedTags.delete(tag);
      } else {
        selectedTags.add(tag);
      }
      tagsInput.value = '';
      renderTagChips();
      saveDraft();
    });
    tagChipsContainer.appendChild(chip);
  });

  if (!filterText && !showingAllTags && visibleTags.length > INITIAL_CHIPS_COUNT) {
    tagSuggestions.hidden = false;
    const link = document.createElement('button');
    link.type = 'button';
    link.className = 'show-all-link';
    link.textContent = `Show all (${visibleTags.length})`;
    link.addEventListener('click', () => {
      showingAllTags = true;
      renderTagChips();
    });
    tagSuggestions.appendChild(link);
  } else {
    tagSuggestions.hidden = true;
  }

  if (showingAllTags && !filterText && tagsToShow.length > INITIAL_CHIPS_COUNT) {
    tagChipsContainer.classList.add('all-tags');
  } else {
    tagChipsContainer.classList.remove('all-tags');
  }

  const hasNonDefaultSelected = [...selectedTags].some(t => !defaultTagSet.has(t));
  clearTagsBtn.hidden = !hasNonDefaultSelected;
}

// --- Save handling ---

function getSelectedTags() {
  return [...selectedTags];
}

function flashButtonSuccess(btn, originalText) {
  clearTimeout(flashTimerId);
  btn.textContent = '\u2713 Saved';
  btn.classList.add('btn-success');
  btn.disabled = false;
  flashTimerId = setTimeout(() => {
    btn.textContent = originalText;
    btn.classList.remove('btn-success');
  }, 2000);
}

export async function handleSave(e) {
  e.preventDefault();
  if (!limits) {
    showSaveStatus("Can't load account limits", 'error');
    return;
  }
  saving = true;
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving...';
  saveStatus.hidden = true;

  const tags = getSelectedTags();
  const bookmark = {
    url: urlInput.value,
    title: titleInput.value,
    description: descriptionInput.value,
    content: truncateByCodePoints(pageContent, limits.max_bookmark_content_length),
    tags
  };

  let success = false;
  try {
    const response = await chrome.runtime.sendMessage({ type: 'CREATE_BOOKMARK', bookmark });

    if (response?.success) {
      success = true;
      flashButtonSuccess(saveBtn, 'Save Bookmark');
      chrome.storage.local.set({ lastUsedTags: tags });
      clearDraft();
    } else if (response) {
      handleSaveError(response);
    } else {
      showSaveStatus("Can't reach extension — try reloading", 'error');
    }
  } catch {
    showSaveStatus("Can't reach extension — try reloading", 'error');
  } finally {
    saving = false;
    if (!success) {
      saveBtn.textContent = 'Save Bookmark';
      updateSaveButtonState();
    }
  }
}

export function handleSaveError(response) {
  const { status, body, retryAfter } = response;

  if (status === 400 || status === 422) {
    let message = 'Invalid bookmark data';
    if (Array.isArray(body?.detail)) {
      message = body.detail.map(e => e.msg).join('; ');
    } else if (typeof body?.detail === 'string') {
      message = body.detail;
    }
    showSaveStatus(message, 'error');
    return;
  }

  if (status === 401 || response.authRequired) {
    const { message, link } = authFailureMessage(response);
    showSaveStatus(message, 'error', link);
    return;
  }

  if (status === 402) {
    const resource = body?.resource;
    const limit = body?.limit;
    const message = resource && limit != null
      ? `You've reached the limit of ${limit} ${resource}s.`
      : 'Bookmark limit reached.';
    showSaveStatus(message, 'error', {
      text: 'Manage your plan',
      href: 'https://tiddly.me/pricing'
    });
    return;
  }

  if (status === 409) {
    if (body?.error_code === 'ARCHIVED_URL_EXISTS' && body?.existing_bookmark_id) {
      showSaveStatus('This bookmark is archived.', 'info', {
        text: 'View it',
        href: `https://tiddly.me/app/bookmarks/${encodeURIComponent(body.existing_bookmark_id)}`
      });
    } else {
      showSaveStatus('Already saved', 'info');
    }
    return;
  }

  if (status === 429) {
    const seconds = retryAfter || '?';
    showSaveStatus(`Rate limited — try again in ${seconds}s.`, 'error', {
      text: 'Higher limits available',
      href: 'https://tiddly.me/pricing'
    });
    return;
  }

  if (status === 451) {
    showSaveStatus('Accept terms first.', 'error', {
      text: 'Open Tiddly',
      href: 'https://tiddly.me'
    });
    return;
  }

  showSaveStatus(
    response.error || `Unexpected error (${status || 'network'})`,
    'error'
  );
}

// --- Search view ---

function triggerSearch() {
  searchOffset = 0;
  loadBookmarks(searchInput.value.trim(), 0, false);
}

function renderTagDropdown() {
  const filter = searchTagInput.value.trim().toLowerCase();
  const available = searchAvailableTags.filter(
    t => !searchFilterTags.has(t) && (!filter || t.includes(filter))
  );

  searchTagDropdown.replaceChildren();

  if (available.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'search-tag-dropdown-empty';
    empty.textContent = filter ? 'No matching tags' : 'No more tags';
    searchTagDropdown.appendChild(empty);
  } else {
    for (const tag of available) {
      const item = document.createElement('div');
      item.className = 'search-tag-dropdown-item';
      item.textContent = tag;
      item.addEventListener('mousedown', (e) => {
        e.preventDefault(); // prevent blur
        searchFilterTags.add(tag);
        searchTagInput.value = '';
        searchTagDropdown.hidden = true;
        searchTagInput.blur();
        refreshActiveTags();
        triggerSearch();
      });
      searchTagDropdown.appendChild(item);
    }
  }
}

function showTagDropdown() {
  renderTagDropdown();
  searchTagDropdown.hidden = false;
}

function refreshActiveTags() {
  searchActiveTags.replaceChildren();
  for (const tag of searchFilterTags) {
    const chip = document.createElement('span');
    chip.className = 'search-active-tag';
    chip.textContent = tag;
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'remove-tag';
    removeBtn.textContent = '\u00d7';
    removeBtn.setAttribute('aria-label', `Remove tag ${tag}`);
    removeBtn.addEventListener('click', () => {
      searchFilterTags.delete(tag);
      refreshActiveTags();
      triggerSearch();
    });
    chip.appendChild(removeBtn);
    searchActiveTags.appendChild(chip);
  }
}

export async function initSearchView({ focus = true } = {}) {
  // Fetch tags for the filter dropdown
  chrome.runtime.sendMessage({ type: 'GET_TAGS' }).then(result => {
    if (result?.success && Array.isArray(result.data?.tags)) {
      searchAvailableTags = result.data.tags.map(t => t.name);
    }
  }).catch(() => {});

  // Initial search
  loadBookmarks('', 0, false);

  searchInput.addEventListener('input', () => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      triggerSearch();
    }, 300);
  });

  searchTagInput.addEventListener('focus', () => {
    showTagDropdown();
  });

  searchTagInput.addEventListener('input', () => {
    showTagDropdown();
  });

  searchTagInput.addEventListener('blur', () => {
    searchTagDropdown.hidden = true;
  });

  searchSortSelect.addEventListener('change', () => {
    searchSort = searchSortSelect.value;
    triggerSearch();
  });

  loadMoreBtn.addEventListener('click', () => {
    loadBookmarks(searchInput.value.trim(), searchOffset, true);
  });

  // Opt-out so the arrow-key tablist handler can preserve focus on the tab button.
  if (focus) {
    searchInput.focus();
  }
}

export async function loadBookmarks(query, offset, append) {
  const requestId = ++searchRequestId;
  loadMoreBtn.hidden = true;
  if (!append) {
    loadMoreBtn.disabled = true;
    searchLoading.hidden = false;
    searchResults.replaceChildren();
  }

  const sortOrder = searchSort === 'title' ? 'asc' : 'desc';
  const message = {
    type: 'SEARCH_BOOKMARKS',
    query,
    offset,
    limit: 10,
    sort_by: searchSort,
    sort_order: sortOrder,
  };
  if (searchFilterTags.size > 0) {
    message.tags = [...searchFilterTags];
  }

  let response;
  try {
    response = await chrome.runtime.sendMessage(message);
  } catch {
    response = null;
  }

  if (requestId !== searchRequestId) return;

  searchLoading.hidden = true;
  loadMoreBtn.disabled = false;

  if (!response?.success) {
    const msg = document.createElement('p');
    msg.className = 'empty-state';
    if (response?.status === 401 || response?.authRequired) {
      msg.textContent = authFailureMessage(response).message;
    } else {
      msg.textContent = "Can't reach server — check your connection";
    }
    searchResults.appendChild(msg);
    if (append) loadMoreBtn.hidden = false;
    return;
  }

  const items = response.data?.items ?? [];
  const has_more = response.data?.has_more ?? false;

  if (items.length === 0 && !append) {
    const msg = document.createElement('p');
    msg.className = 'empty-state';
    msg.textContent = query ? 'No results' : 'No bookmarks yet';
    searchResults.appendChild(msg);
    return;
  }

  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'search-result';

    const titleRow = document.createElement('div');
    titleRow.className = 'search-result-title-row';

    const favicon = document.createElement('img');
    favicon.className = 'search-result-favicon';
    favicon.width = 16;
    favicon.height = 16;
    favicon.src = `chrome-extension://${chrome.runtime.id}/_favicon/?pageUrl=${encodeURIComponent(item.url)}&size=32`;
    favicon.alt = '';
    favicon.onerror = () => favicon.remove();
    titleRow.appendChild(favicon);

    const title = document.createElement('a');
    title.className = 'search-result-title';
    title.textContent = item.title || item.url;
    title.href = item.url;
    title.target = '_blank';
    title.rel = 'noopener noreferrer';
    title.addEventListener('click', (e) => {
      e.preventDefault();
      chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
        if (tab?.id) {
          chrome.tabs.update(tab.id, { url: item.url });
        }
        window.close();
      });
    });
    titleRow.appendChild(title);
    el.appendChild(titleRow);

    const url = document.createElement('div');
    url.className = 'search-result-url';
    url.textContent = item.url;
    el.appendChild(url);

    const meta = document.createElement('div');
    meta.className = 'search-result-meta';

    if (item.tags && item.tags.length > 0) {
      item.tags.forEach(t => {
        const tag = document.createElement('span');
        tag.className = 'search-result-tag';
        tag.textContent = t;
        meta.appendChild(tag);
      });
    }

    if (meta.childNodes.length > 0) {
      el.appendChild(meta);
    }

    searchResults.appendChild(el);
  });

  searchOffset = offset + items.length;
  loadMoreBtn.hidden = !has_more;
}
