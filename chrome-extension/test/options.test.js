import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OPTIONS_HTML = fs.readFileSync(path.join(__dirname, '..', 'options.html'), 'utf-8');

function primeStorage(initial = {}) {
  const store = { ...initial };
  chrome.storage.local.get.mockImplementation((keys) => {
    const result = {};
    for (const key of keys) {
      if (key in store) result[key] = store[key];
    }
    return Promise.resolve(result);
  });
  chrome.storage.local.set.mockImplementation((items) => {
    Object.assign(store, items);
    return Promise.resolve();
  });
  return store;
}

async function loadOptions() {
  document.body.innerHTML = OPTIONS_HTML;
  vi.resetModules();
  await import('../options.js');
  await settleMicrotasks();
}

async function clickSaveAndSettle() {
  document.getElementById('save-btn').click();
  await settleMicrotasks();
}

async function settleMicrotasks() {
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0));
}

// The options page loads tags only under a known account. GET_AUTH_STATUS
// carries the principal; GET_TAGS success responses must carry a matching
// principal or the late-response guard discards them.
const PAT_STATUS = { activeMode: 'pat', hasPat: true, hasSession: false, principal: 'pat:optionstest0000' };
const NONE_STATUS = { activeMode: 'none', hasPat: false, hasSession: false, principal: null };
const PRINCIPAL = PAT_STATUS.principal;

// Status reflects whether a token is stored (as real auth does), so init with
// no token doesn't fire a tags load before the test's save clicks.
function statusFor(store) {
  return store.token ? PAT_STATUS : NONE_STATUS;
}

describe('options — token validation status', () => {
  it('shows "Token saved but appears invalid" when GET_TAGS returns 401', async () => {
    const store = primeStorage({});
    chrome.runtime.sendMessage.mockImplementation((msg) =>
      msg.type === 'GET_AUTH_STATUS'
        ? Promise.resolve(statusFor(store))
        : Promise.resolve({ success: false, status: 401 }));

    await loadOptions();

    document.getElementById('token').value = 'bm_bad';
    await clickSaveAndSettle();

    const saveStatus = document.getElementById('save-status');
    expect(saveStatus.hidden).toBe(false);
    expect(saveStatus.textContent).toContain('invalid');
  });

  it('clears the stale 401 error when a subsequent valid token loads tags', async () => {
    const store = primeStorage({});
    let tagsCall = 0;
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') return Promise.resolve(statusFor(store));
      if (msg.type !== 'GET_TAGS') return Promise.resolve(null);
      tagsCall++;
      if (tagsCall === 1) return Promise.resolve({ success: false, status: 401 });
      return Promise.resolve({ success: true, data: { tags: [{ name: 'alpha' }, { name: 'beta' }] }, principal: PRINCIPAL });
    });

    await loadOptions();

    // First save — invalid token surfaces the error.
    document.getElementById('token').value = 'bm_bad';
    await clickSaveAndSettle();
    const saveStatus = document.getElementById('save-status');
    expect(saveStatus.hidden).toBe(false);

    // Second save — valid token; stale error must clear and tags must render.
    document.getElementById('token').value = 'bm_good';
    await clickSaveAndSettle();

    expect(saveStatus.hidden).toBe(true);
    const chips = document.querySelectorAll('#tag-chips .tag-chip');
    expect(chips.length).toBe(2);
  });

  it('clears the stale 401 error even when the second attempt hits a network failure', async () => {
    const store = primeStorage({});
    let tagsCall = 0;
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') return Promise.resolve(statusFor(store));
      if (msg.type !== 'GET_TAGS') return Promise.resolve(null);
      tagsCall++;
      if (tagsCall === 1) return Promise.resolve({ success: false, status: 401 });
      return Promise.resolve({ success: false, status: 500 });
    });

    await loadOptions();

    document.getElementById('token').value = 'bm_bad';
    await clickSaveAndSettle();
    expect(document.getElementById('save-status').hidden).toBe(false);

    document.getElementById('token').value = 'bm_retry';
    await clickSaveAndSettle();

    // saveStatus must be reset regardless of the second outcome; the retry's
    // server-side failure surfaces via tagsStatus instead.
    expect(document.getElementById('save-status').hidden).toBe(true);
    expect(document.getElementById('tags-status').textContent).toContain('Could not load');
  });
});

describe('options — connection status', () => {
  it('session + token: both-configured copy with a working remove-token action', async () => {
    const store = primeStorage({ token: 'bm_x' });
    chrome.storage.local.remove.mockImplementation((keys) => {
      for (const k of keys) delete store[k];
      return Promise.resolve();
    });
    chrome.runtime.sendMessage.mockImplementation(async (msg) => {
      if (msg.type === 'GET_AUTH_STATUS') {
        return store.token
          ? { activeMode: 'clerk', hasPat: true, hasSession: true }
          : { activeMode: 'clerk', hasPat: false, hasSession: true };
      }
      return { success: true, data: { tags: [] } };
    });
    await loadOptions();

    expect(document.getElementById('auth-status-text').textContent).toContain('web session');
    const btn = document.getElementById('remove-token-btn');
    expect(btn.hidden).toBe(false);

    btn.click();
    await settleMicrotasks();

    expect(store.token).toBeUndefined();
    expect(document.getElementById('token').value).toBe('');
    expect(document.getElementById('remove-token-btn').hidden).toBe(true);
    expect(document.getElementById('auth-status-text').textContent).toContain('no token needed');
  });

  it('token only: token-active copy without the remove button', async () => {
    primeStorage({ token: 'bm_x' });
    chrome.runtime.sendMessage.mockImplementation(async (msg) =>
      msg.type === 'GET_AUTH_STATUS'
        ? { activeMode: 'pat', hasPat: true, hasSession: false }
        : { success: true, data: { tags: [] } });
    await loadOptions();

    expect(document.getElementById('auth-status-text').textContent).toContain('saved access token');
    expect(document.getElementById('remove-token-btn').hidden).toBe(true);
  });

  it('nothing configured: not-connected copy', async () => {
    primeStorage({});
    await loadOptions();

    expect(document.getElementById('auth-status-text').textContent).toContain('Not connected');
  });
});

describe('options — principal transitions (per-account isolation)', () => {
  const A = { activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:accountA00000000' };
  const B = { activeMode: 'clerk', hasPat: false, hasSession: true, principal: 'clerk:accountB00000000' };

  it('on a web account switch, resets to the new account’s defaults — A’s tag selections do not carry to B', async () => {
    const store = primeStorage({
      'defaultTags:clerk:accountA00000000': ['a-only-tag'],
      'defaultTags:clerk:accountB00000000': ['b-only-tag'],
    });
    let current = A;
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') return Promise.resolve(current);
      if (msg.type === 'GET_TAGS') {
        return Promise.resolve({ success: true, data: { tags: [{ name: 'a-only-tag' }, { name: 'b-only-tag' }] }, principal: current.principal });
      }
      return Promise.resolve(null);
    });

    await loadOptions();
    // A's default is selected.
    const selectedA = [...document.querySelectorAll('#tag-chips .tag-chip.selected')].map(c => c.textContent);
    expect(selectedA).toEqual(['a-only-tag']);

    // The web account switches to B; a visibility change reconciles.
    current = B;
    document.dispatchEvent(new Event('visibilitychange'));
    await settleMicrotasks();

    const selectedB = [...document.querySelectorAll('#tag-chips .tag-chip.selected')].map(c => c.textContent);
    expect(selectedB).toEqual(['b-only-tag']);
    expect(selectedB).not.toContain('a-only-tag');
  });

  it('a slow STATUS resolution for A that lands after a newer B reconciliation does not revert the page to A', async () => {
    primeStorage({
      'defaultTags:clerk:accountA00000000': ['a-only-tag'],
      'defaultTags:clerk:accountB00000000': ['b-only-tag'],
    });
    let releaseAStatus;
    const aStatusGate = new Promise((r) => { releaseAStatus = r; });
    // Positive synchronization: resolves only when B's reconciliation
    // OBSERVABLY ran (its tags fetch carries B's principal) — so the test
    // can't pass on an empty, never-reconciled page.
    let signalBTags;
    const bTagsSeen = new Promise((r) => { signalBTags = r; });
    let statusCall = 0;
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') {
        statusCall++;
        // The FIRST status request (A's reconciliation, from init) hangs;
        // every later one (B's, from visibilitychange) resolves immediately.
        return statusCall === 1 ? aStatusGate.then(() => A) : Promise.resolve(B);
      }
      if (msg.type === 'GET_TAGS') {
        const p = msg.expectedPrincipal;
        if (p === B.principal) signalBTags();
        return Promise.resolve({ success: true, data: { tags: [{ name: 'a-only-tag' }, { name: 'b-only-tag' }] }, principal: p });
      }
      return Promise.resolve(null);
    });

    // Init starts A's reconciliation (status hangs) …
    const optionsReady = loadOptions();
    // … then a newer B reconciliation starts and completes.
    document.dispatchEvent(new Event('visibilitychange'));
    await bTagsSeen;
    await settleMicrotasks();

    // B's state is POSITIVELY applied before A ever resolves.
    let selected = [...document.querySelectorAll('#tag-chips .tag-chip.selected')].map(c => c.textContent);
    expect(selected).toEqual(['b-only-tag']);

    // Now A's stale status finally lands — it must change nothing.
    releaseAStatus();
    await optionsReady;
    await settleMicrotasks();

    selected = [...document.querySelectorAll('#tag-chips .tag-chip.selected')].map(c => c.textContent);
    expect(selected).toEqual(['b-only-tag']);
    expect(selected).not.toContain('a-only-tag');
  });

  it('ignores a slow tags response for A that resolves after switching to B', async () => {
    primeStorage({});
    let current = A;
    let releaseA;
    const aTagsGate = new Promise((r) => { releaseA = r; });
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      if (msg.type === 'GET_AUTH_STATUS') return Promise.resolve(current);
      if (msg.type === 'GET_TAGS') {
        // A's tags hang; B's resolve immediately.
        if (current === A) return aTagsGate.then(() => ({ success: true, data: { tags: [{ name: 'a-stale-tag' }] }, principal: A.principal }));
        return Promise.resolve({ success: true, data: { tags: [{ name: 'b-live-tag' }] }, principal: B.principal });
      }
      return Promise.resolve(null);
    });

    await loadOptions(); // fires A's (hanging) tags load
    current = B;
    document.dispatchEvent(new Event('visibilitychange'));
    await settleMicrotasks(); // B resolves and renders

    // Now A's slow response arrives — it must be discarded, not repaint B.
    releaseA();
    await settleMicrotasks();

    const rendered = [...document.querySelectorAll('#tag-chips .tag-chip')].map(c => c.textContent);
    expect(rendered).toContain('b-live-tag');
    expect(rendered).not.toContain('a-stale-tag');
  });
});
