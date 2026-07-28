import { ownedKey, migrateLegacyOwnedCaches } from './cache-ownership.js';

const authStatusText = document.getElementById('auth-status-text');
const removeTokenBtn = document.getElementById('remove-token-btn');
const tokenInput = document.getElementById('token');
const toggleTokenBtn = document.getElementById('toggle-token');
const saveBtn = document.getElementById('save-btn');
const tokenError = document.getElementById('token-error');
const saveStatus = document.getElementById('save-status');
const tagsSection = document.getElementById('tags-section');
const tagChipsContainer = document.getElementById('tag-chips');
const tagsStatus = document.getElementById('tags-status');

let allTags = [];
let selectedTags = new Set();
// The account whose default tags this page reads/writes — the fresh auth
// principal. Default tags are namespaced per account (via the shared
// cache-ownership contract), so one account's tag vocabulary never leaks into
// another's saves.
let currentPrincipal = null;
// Monotonic transition counter. A long-lived options tab can see the web
// account change out from under it; any in-flight async work captures the
// generation at start and discards its result if a transition happened since,
// so an account-A tags response can't repaint account B's UI.
let principalGeneration = 0;

// PURE status fetch — no global or DOM mutation, so a stale (slower, older)
// reconciliation resolving late can't clobber a newer one's state as a side
// effect. Only syncToPrincipal, gated on the sync ID, applies anything.
async function fetchAuthStatus() {
  try {
    return await chrome.runtime.sendMessage({ type: 'GET_AUTH_STATUS' });
  } catch {
    return null;
  }
}

// Pure render of the connection copy. Makes the session-wins behavior legible:
// when both a session and a token exist, the session is what's actually in use
// and the token can be removed in one click.
function applyAuthStatusText(status) {
  removeTokenBtn.hidden = true;
  if (!status || status.activeMode === 'none') {
    authStatusText.textContent = 'Not connected. Sign in at tiddly.me, or paste an access token below.';
  } else if (status.activeMode === 'clerk' && status.hasPat) {
    authStatusText.textContent = 'Connected via your tiddly.me web session. A saved token is also configured — it is used when you are signed out.';
    removeTokenBtn.hidden = false;
  } else if (status.activeMode === 'clerk') {
    authStatusText.textContent = 'Connected via your tiddly.me web session — no token needed.';
  } else {
    authStatusText.textContent = 'Using a saved access token. Sign in at tiddly.me to connect automatically.';
  }
}

// The single principal-transition entry point, race-safe: each invocation
// takes a monotonic id and, after EVERY await, bails if a newer sync has since
// started — so only the newest reconciliation ever mutates currentPrincipal,
// the DOM, defaults, or launches a tag load. A stale, slow status resolution
// therefore can't repaint the page as the previous account.
let syncId = 0;
async function syncToPrincipal() {
  const mySync = ++syncId;
  const status = await fetchAuthStatus();
  if (mySync !== syncId) return;

  const previous = currentPrincipal;
  currentPrincipal = status?.principal ?? null;
  applyAuthStatusText(status);
  if (currentPrincipal !== previous) {
    principalGeneration += 1;
    selectedTags = new Set();
    allTags = [];
    tagChipsContainer.replaceChildren();
  }

  const key = ownedKey('defaultTags', currentPrincipal);
  if (key) {
    const stored = await chrome.storage.local.get([key]);
    if (mySync !== syncId) return;
    (stored[key] || []).forEach(t => selectedTags.add(t));
  }
  // Load tags whenever any auth is live — GET_TAGS resolves the credential in
  // the worker.
  if (currentPrincipal) loadTags();
}

removeTokenBtn.addEventListener('click', async () => {
  await chrome.storage.local.remove(['token']);
  tokenInput.value = '';
  await syncToPrincipal();
});

// A web-side account switch can happen while this tab sits in the background;
// reconcile when it becomes visible again.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') syncToPrincipal();
});

async function init() {
  await migrateLegacyOwnedCaches();
  const { token } = await chrome.storage.local.get(['token']);
  if (token) tokenInput.value = token;
  await syncToPrincipal();
}

init();

// Show/hide token toggle
toggleTokenBtn.addEventListener('click', () => {
  const isPassword = tokenInput.type === 'password';
  tokenInput.type = isPassword ? 'text' : 'password';
  toggleTokenBtn.textContent = isPassword ? 'Hide' : 'Show';
});

// Save token
saveBtn.addEventListener('click', () => {
  const token = tokenInput.value.trim();

  tokenError.hidden = true;
  if (!token) {
    showError(tokenError, 'Token is required');
    return;
  }
  if (!token.startsWith('bm_')) {
    showError(tokenError, 'Token should start with bm_');
    return;
  }

  chrome.storage.local.set({ token }).then(async () => {
    flashButtonSuccess(saveBtn, 'Save');
    // The new token may change the active principal (e.g. none → PAT); route
    // through the transition so tag state resets to the current owner.
    await syncToPrincipal();
  });
});

async function loadTags() {
  const generation = principalGeneration;
  const requestPrincipal = currentPrincipal;
  // Clear any stale outcome from a previous save attempt so each retry starts fresh.
  saveStatus.hidden = true;
  tagsSection.hidden = false;
  tagsStatus.hidden = false;
  tagsStatus.textContent = 'Loading tags...';

  try {
    const response = await chrome.runtime.sendMessage({ type: 'GET_TAGS', expectedPrincipal: requestPrincipal });
    // Discard if the account transitioned while this was in flight, or if the
    // worker served a different principal than we asked for — either way the
    // result belongs to an account this UI no longer represents.
    if (generation !== principalGeneration) return;
    if (response?.success && response.principal !== requestPrincipal) return;
    if (response?.success && Array.isArray(response.data?.tags)) {
      allTags = response.data.tags.map(t => t.name);
      tagsStatus.hidden = true;
      renderTagChips();
    } else if (response?.principalChanged) {
      tagsStatus.textContent = 'Your account changed — reopen settings.';
      tagChipsContainer.replaceChildren();
    } else if (response?.status === 401) {
      showStatus(saveStatus, 'Token saved but appears invalid', 'error');
      tagsStatus.hidden = true;
      tagChipsContainer.replaceChildren();
    } else {
      tagsStatus.textContent = 'Could not load tags';
      tagChipsContainer.replaceChildren();
    }
  } catch {
    if (generation !== principalGeneration) return;
    tagsStatus.textContent = 'Could not connect';
    tagChipsContainer.replaceChildren();
  }
}

function renderTagChips() {
  tagChipsContainer.replaceChildren();

  // Show all tags, selected first
  const sorted = [...allTags].sort((a, b) => {
    const aSelected = selectedTags.has(a) ? 0 : 1;
    const bSelected = selectedTags.has(b) ? 0 : 1;
    return aSelected - bSelected;
  });

  sorted.forEach(tag => {
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
      renderTagChips();
      const key = ownedKey('defaultTags', currentPrincipal);
      if (key) chrome.storage.local.set({ [key]: [...selectedTags] });
    });
    tagChipsContainer.appendChild(chip);
  });
}

let flashTimerId = null;

function flashButtonSuccess(btn, originalText) {
  clearTimeout(flashTimerId);
  btn.textContent = '\u2713 Saved';
  btn.classList.add('btn-success');
  flashTimerId = setTimeout(() => {
    btn.textContent = originalText;
    btn.classList.remove('btn-success');
  }, 2000);
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}

let statusTimerId = null;

function showStatus(el, message, type) {
  clearTimeout(statusTimerId);
  el.textContent = message;
  el.className = `status ${type}`;
  el.hidden = false;
  if (type === 'success') {
    statusTimerId = setTimeout(() => { el.hidden = true; }, 3000);
  }
}
