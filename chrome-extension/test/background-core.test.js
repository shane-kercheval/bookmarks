// The Clerk SDK is mocked at the module boundary (the plan's test-target
// decision: unit tests on source with the SDK mocked; the real SDK is
// exercised by the built artifact in the manual pass).
const { createClerkClient } = vi.hoisted(() => ({ createClerkClient: vi.fn() }));
vi.mock('@clerk/chrome-extension/client', () => ({ createClerkClient }));

import {
  API_URL,
  handleGetLimits,
  handleGetTags,
  handleCreateBookmark,
  handleSearchBookmarks,
  getToken,
  resolveAuth,
  getAuthStatus,
} from '../background-core.js';

function mockClerkSession(token) {
  createClerkClient.mockResolvedValue({
    session: token === null ? null : { getToken: vi.fn().mockResolvedValue(token) },
  });
}

// Default for every test: no live session, so the pre-existing handler tests
// exercise the PAT path unchanged. Reset first — the hoisted mock outlives
// individual tests, so call history would otherwise accumulate across them.
beforeEach(() => {
  createClerkClient.mockReset();
  mockClerkSession(null);
});

// --- Fetch mock helper ---

function mockFetch(status, body, headers = {}) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      headers: { get: (name) => headers[name] ?? null },
    })
  );
}

function mockFetchError(error) {
  globalThis.fetch = vi.fn(() => Promise.reject(error));
}

describe('getToken', () => {
  it('returns the stored token', async () => {
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    const token = await getToken();
    expect(token).toBe('my-pat');
  });

  it('throws when no token is configured', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(getToken()).rejects.toThrow('Not signed in');
  });
});

describe('handleGetLimits', () => {
  beforeEach(() => {
    chrome.storage.local.get.mockResolvedValue({ token: 'test-token' });
  });

  it('calls correct endpoint with auth headers', async () => {
    const limitsData = { max_title_length: 100, max_description_length: 1000, max_bookmark_content_length: 100000 };
    mockFetch(200, limitsData);

    await handleGetLimits();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${API_URL}/users/me/limits`,
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer test-token',
          'X-Request-Source': 'chrome-extension',
        }),
      })
    );
  });

  it('returns { success: true, data } on 200', async () => {
    const limitsData = { max_title_length: 100 };
    mockFetch(200, limitsData);

    const result = await handleGetLimits();

    expect(result).toEqual({ success: true, status: 200, data: limitsData, authMode: 'pat' });
  });

  it('returns { success: false, status } on non-200', async () => {
    mockFetch(403, {});

    const result = await handleGetLimits();

    expect(result).toEqual({ success: false, status: 403, body: {}, retryAfter: null, authMode: 'pat' });
  });

  it('throws on missing token', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(handleGetLimits()).rejects.toThrow('Not signed in');
  });
});

describe('handleGetTags', () => {
  beforeEach(() => {
    chrome.storage.local.get.mockResolvedValue({ token: 'test-token' });
  });

  it('returns { success: true, data } on 200', async () => {
    const tagsData = { tags: [{ name: 'js' }] };
    mockFetch(200, tagsData);

    const result = await handleGetTags();

    expect(result).toEqual({ success: true, status: 200, data: tagsData, authMode: 'pat' });
  });

  it('returns { success: false, status } on non-200', async () => {
    mockFetch(500, {});

    const result = await handleGetTags();

    expect(result).toEqual({ success: false, status: 500, body: {}, retryAfter: null, authMode: 'pat' });
  });

  it('throws on missing token', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(handleGetTags()).rejects.toThrow('Not signed in');
  });
});

describe('handleCreateBookmark', () => {
  beforeEach(() => {
    chrome.storage.local.get.mockResolvedValue({ token: 'test-token' });
  });

  it('sends correct payload and returns success', async () => {
    const bookmark = { url: 'https://example.com', title: 'Test', description: '', tags: [] };
    const responseData = { id: '123', ...bookmark };
    mockFetch(201, responseData);

    const result = await handleCreateBookmark({ bookmark });

    expect(result).toEqual({ success: true, bookmark: responseData, authMode: 'pat' });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${API_URL}/bookmarks/`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(bookmark),
      })
    );
  });

  it('returns error response with status, body, and retryAfter', async () => {
    mockFetch(429, { detail: 'Too many requests' }, { 'Retry-After': '60' });

    const result = await handleCreateBookmark({ bookmark: {} });

    expect(result.success).toBe(false);
    expect(result.status).toBe(429);
    expect(result.body).toEqual({ detail: 'Too many requests' });
    expect(result.retryAfter).toBe('60');
  });

  it('throws on missing token', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(handleCreateBookmark({ bookmark: {} })).rejects.toThrow('Not signed in');
  });
});

describe('handleSearchBookmarks', () => {
  beforeEach(() => {
    chrome.storage.local.get.mockResolvedValue({ token: 'test-token' });
  });

  it('returns search results on success', async () => {
    const data = { items: [{ id: '1', url: 'https://example.com' }], has_more: false };
    mockFetch(200, data);

    const result = await handleSearchBookmarks({ query: 'test', limit: 10, offset: 0 });

    expect(result).toEqual({ success: true, status: 200, data, authMode: 'pat' });
  });

  it('passes query params correctly', async () => {
    mockFetch(200, { items: [] });

    await handleSearchBookmarks({ query: 'hello', limit: 5, offset: 10 });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('q=hello');
    expect(url).toContain('limit=5');
    expect(url).toContain('offset=10');
  });

  it('does not set sort_by or sort_order when not provided', async () => {
    mockFetch(200, { items: [] });

    await handleSearchBookmarks({ limit: 10, offset: 0 });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).not.toContain('sort_by=');
    expect(url).not.toContain('sort_order=');
    expect(url).not.toContain('q=');
  });

  it('passes sort_by and sort_order when provided', async () => {
    mockFetch(200, { items: [] });

    await handleSearchBookmarks({ query: 'test', limit: 10, offset: 0, sort_by: 'title', sort_order: 'asc' });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('sort_by=title');
    expect(url).toContain('sort_order=asc');
  });

  it('passes tags as repeated params with tag_match', async () => {
    mockFetch(200, { items: [] });

    await handleSearchBookmarks({ limit: 10, offset: 0, tags: ['python', 'rust'] });

    const url = globalThis.fetch.mock.calls[0][0];
    const params = new URL(url).searchParams;
    expect(params.getAll('tags')).toEqual(['python', 'rust']);
    expect(params.get('tag_match')).toBe('all');
  });

  it('uses custom tag_match when provided', async () => {
    mockFetch(200, { items: [] });

    await handleSearchBookmarks({ limit: 10, offset: 0, tags: ['python'], tag_match: 'any' });

    const url = globalThis.fetch.mock.calls[0][0];
    const params = new URL(url).searchParams;
    expect(params.get('tag_match')).toBe('any');
  });

  it('does not add tags params when tags array is empty', async () => {
    mockFetch(200, { items: [] });

    await handleSearchBookmarks({ limit: 10, offset: 0, tags: [] });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).not.toContain('tags=');
    expect(url).not.toContain('tag_match=');
  });

  it('backward compat: message without tags/sort still works', async () => {
    const data = { items: [{ id: '1' }], has_more: false };
    mockFetch(200, data);

    const result = await handleSearchBookmarks({ query: 'test', limit: 10, offset: 0 });

    expect(result).toEqual({ success: true, status: 200, data, authMode: 'pat' });
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('q=test');
    expect(url).toContain('limit=10');
  });
});

describe('auth resolution (session wins; PAT is the fallback)', () => {
  it('uses the session token even when a PAT is configured', async () => {
    mockClerkSession('sess-jwt');
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(getToken()).resolves.toBe('sess-jwt');
  });

  it('falls back to the PAT when there is no live session', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(getToken()).resolves.toBe('my-pat');
  });

  it('falls back to the PAT when Clerk client creation fails', async () => {
    createClerkClient.mockRejectedValue(new Error('sync host unreachable'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(getToken()).resolves.toBe('my-pat');
  });

  it('falls back to the PAT when the session token fetch fails', async () => {
    createClerkClient.mockResolvedValue({
      session: { getToken: vi.fn().mockRejectedValue(new Error('token refresh failed')) },
    });
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(getToken()).resolves.toBe('my-pat');
  });

  it('errors cleanly when Clerk fails and no PAT exists', async () => {
    createClerkClient.mockRejectedValue(new Error('init failure'));
    chrome.storage.local.get.mockResolvedValue({});

    await expect(getToken()).rejects.toThrow('Not signed in');
  });

  it('surfaces a server 401 on the session path without retrying with the PAT', async () => {
    mockClerkSession('sess-jwt');
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    mockFetch(401, {});

    const result = await handleGetLimits();

    expect(result).toEqual({ success: false, status: 401, body: {}, retryAfter: null, authMode: 'clerk' });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer sess-jwt');
  });

  it('coalesces concurrent requests into one client initialization', async () => {
    mockClerkSession('sess-jwt');

    const [a, b] = await Promise.all([getToken(), getToken()]);

    expect(a).toBe('sess-jwt');
    expect(b).toBe('sess-jwt');
    expect(createClerkClient).toHaveBeenCalledTimes(1);
  });

  it('sequential requests each initialize fresh (per-request session freshness)', async () => {
    // The SDK deliberately bypasses its singleton for background scope; only
    // in-flight initializations are shared — a resolved client is never
    // retained across distinct interactions (web sign-out must be observed).
    mockClerkSession('sess-jwt');

    await getToken();
    await getToken();

    expect(createClerkClient).toHaveBeenCalledTimes(2);
  });

  it('a PAT failure carries authMode pat in the envelope', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    mockFetch(401, { detail: 'Invalid token' });

    const result = await handleGetTags();

    expect(result.authMode).toBe('pat');
    expect(result.status).toBe(401);
    expect(result.body).toEqual({ detail: 'Invalid token' });
  });

  it('passes the account_deleted terminal error body through on non-create handlers', async () => {
    mockClerkSession('sess-jwt');
    mockFetch(401, { detail: 'This account was deleted', error_code: 'account_deleted' });

    const result = await handleGetTags();

    expect(result.success).toBe(false);
    expect(result.body.error_code).toBe('account_deleted');
    expect(result.authMode).toBe('clerk');
  });

  it('a failed Clerk call never poisons a later one (worker-lifetime resilience)', async () => {
    createClerkClient.mockRejectedValueOnce(new Error('transient failure'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    await expect(getToken()).resolves.toBe('my-pat');

    mockClerkSession('sess-jwt');
    await expect(getToken()).resolves.toBe('sess-jwt');
  });

  it('resolves fresh after a worker restart (module state rebuilt)', async () => {
    vi.resetModules();
    const fresh = await import('../background-core.js');
    mockClerkSession('sess-jwt-after-restart');

    await expect(fresh.getToken()).resolves.toBe('sess-jwt-after-restart');
  });

  it('resolveAuth reports none when nothing is configured', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({});

    await expect(resolveAuth()).resolves.toEqual({ mode: 'none', token: null });
  });
});

describe('getAuthStatus (status only — never a token)', () => {
  it.each([
    ['both configured → session active', 'sess-jwt', 'my-pat', { activeMode: 'clerk', hasPat: true, hasSession: true }],
    ['session only', 'sess-jwt', undefined, { activeMode: 'clerk', hasPat: false, hasSession: true }],
    ['PAT only', null, 'my-pat', { activeMode: 'pat', hasPat: true, hasSession: false }],
    ['neither', null, undefined, { activeMode: 'none', hasPat: false, hasSession: false }],
  ])('%s', async (_label, sessionToken, pat, expected) => {
    mockClerkSession(sessionToken);
    chrome.storage.local.get.mockResolvedValue(pat ? { token: pat } : {});

    const status = await getAuthStatus();

    expect(status).toEqual(expected);
    // The exact-equality assertion above is the guarantee; make the security
    // property explicit too: no token material in any status field.
    expect(JSON.stringify(status)).not.toContain('sess-jwt');
    expect(JSON.stringify(status)).not.toContain('my-pat');
  });
});
