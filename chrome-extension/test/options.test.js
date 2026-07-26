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

describe('options — token validation status', () => {
  it('shows "Token saved but appears invalid" when GET_TAGS returns 401', async () => {
    primeStorage({});
    chrome.runtime.sendMessage.mockResolvedValue({ success: false, status: 401 });

    await loadOptions();

    document.getElementById('token').value = 'bm_bad';
    await clickSaveAndSettle();

    const saveStatus = document.getElementById('save-status');
    expect(saveStatus.hidden).toBe(false);
    expect(saveStatus.textContent).toContain('invalid');
  });

  it('clears the stale 401 error when a subsequent valid token loads tags', async () => {
    primeStorage({});
    let tagsCall = 0;
    chrome.runtime.sendMessage.mockImplementation((msg) => {
      // The status probe (GET_AUTH_STATUS) also flows through here now —
      // discriminate by type so only tag fetches advance the sequence.
      if (msg.type !== 'GET_TAGS') return Promise.resolve(null);
      tagsCall++;
      if (tagsCall === 1) return Promise.resolve({ success: false, status: 401 });
      return Promise.resolve({ success: true, data: { tags: [{ name: 'alpha' }, { name: 'beta' }] } });
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
    primeStorage({});
    let tagsCall = 0;
    chrome.runtime.sendMessage.mockImplementation((msg) => {
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
