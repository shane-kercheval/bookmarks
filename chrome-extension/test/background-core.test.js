// Request-layer tests: the authedRequest envelope, its fail-closed principal
// binding, and the four API handlers. Credential RESOLUTION tests (session-wins,
// coalescing, status) live in auth.test.js — this file mocks the Clerk SDK to a
// fixed state per test.
//
// The auth module holds real state (the in-flight resolution promise), so every
// test gets a fresh module graph via resetModules + dynamic import.
const { createClerkClient } = vi.hoisted(() => ({ createClerkClient: vi.fn() }));
vi.mock('@clerk/chrome-extension/client', () => ({ createClerkClient }));

let API_URL, handleGetLimits, handleGetTags, handleCreateBookmark, handleSearchBookmarks, resolveAuth;

function mockClerkSession(token) {
  createClerkClient.mockResolvedValue({
    session: token === null ? null : { getToken: vi.fn().mockResolvedValue(token) },
  });
}

// A decodable JWT so the session path derives a non-null principal (required
// now that the request boundary fails closed on an unknown principal).
function jwtWithSub(sub) {
  const b64 = (o) => btoa(JSON.stringify(o)).replace(/=+$/, '');
  return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64({ sub })}.sig`;
}

// The request boundary is fail-closed on principal: the popup sends the owner
// it hydrated under, and authedRequest sends nothing unless it matches the
// credential resolved right now. Tests reach the fetch path by sending the
// principal the system itself would resolve — exactly as the popup does.
async function currentPrincipal() {
  return (await resolveAuth()).principal;
}
async function withPrincipal(handler, message = {}) {
  return handler({ ...message, expectedPrincipal: await currentPrincipal() });
}

// Default for every test: no live session, so the handler tests exercise the
// PAT path unless they opt in to a session.
beforeEach(async () => {
  createClerkClient.mockReset();
  mockClerkSession(null);
  vi.resetModules();
  ({
    API_URL,
    handleGetLimits,
    handleGetTags,
    handleCreateBookmark,
    handleSearchBookmarks,
  } = await import('../background-core.js'));
  ({ resolveAuth } = await import('../auth.js'));
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

describe('handleGetLimits', () => {
  beforeEach(() => {
    chrome.storage.local.get.mockResolvedValue({ token: 'test-token' });
  });

  it('calls correct endpoint with auth headers', async () => {
    const limitsData = { max_title_length: 100, max_description_length: 1000, max_bookmark_content_length: 100000 };
    mockFetch(200, limitsData);

    await withPrincipal(handleGetLimits);

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

    const result = await withPrincipal(handleGetLimits);

    expect(result).toMatchObject({ success: true, status: 200, data: limitsData, authMode: 'pat' });
  });

  it('returns { success: false, status } on non-200', async () => {
    mockFetch(403, {});

    const result = await withPrincipal(handleGetLimits);

    expect(result).toMatchObject({ success: false, status: 403, body: {}, retryAfter: null, authMode: 'pat' });
  });

  it('throws with the authRequired flag when no credential exists', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(handleGetLimits()).rejects.toMatchObject({ authRequired: true });
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

    const result = await withPrincipal(handleGetTags);

    expect(result).toMatchObject({ success: true, status: 200, data: tagsData, authMode: 'pat' });
  });

  it('returns { success: false, status } on non-200', async () => {
    mockFetch(500, {});

    const result = await withPrincipal(handleGetTags);

    expect(result).toMatchObject({ success: false, status: 500, body: {}, retryAfter: null, authMode: 'pat' });
  });

  it('throws with the authRequired flag when no credential exists', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(handleGetTags()).rejects.toMatchObject({ authRequired: true });
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

    const result = await withPrincipal(handleCreateBookmark, { bookmark });

    expect(result).toMatchObject({ success: true, bookmark: responseData, authMode: 'pat' });
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

    const result = await withPrincipal(handleCreateBookmark, { bookmark: {} });

    expect(result.success).toBe(false);
    expect(result.status).toBe(429);
    expect(result.body).toEqual({ detail: 'Too many requests' });
    expect(result.retryAfter).toBe('60');
  });

  it('throws with the authRequired flag when no credential exists', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    await expect(handleCreateBookmark({ bookmark: {} })).rejects.toMatchObject({ authRequired: true });
  });
});

describe('handleSearchBookmarks', () => {
  beforeEach(() => {
    chrome.storage.local.get.mockResolvedValue({ token: 'test-token' });
  });

  it('returns search results on success', async () => {
    const data = { items: [{ id: '1', url: 'https://example.com' }], has_more: false };
    mockFetch(200, data);

    const result = await withPrincipal(handleSearchBookmarks, { query: 'test', limit: 10, offset: 0 });

    expect(result).toMatchObject({ success: true, status: 200, data, authMode: 'pat' });
  });

  it('passes query params correctly', async () => {
    mockFetch(200, { items: [] });

    await withPrincipal(handleSearchBookmarks, { query: 'hello', limit: 5, offset: 10 });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('q=hello');
    expect(url).toContain('limit=5');
    expect(url).toContain('offset=10');
  });

  it('does not set sort_by or sort_order when not provided', async () => {
    mockFetch(200, { items: [] });

    await withPrincipal(handleSearchBookmarks, { limit: 10, offset: 0 });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).not.toContain('sort_by=');
    expect(url).not.toContain('sort_order=');
    expect(url).not.toContain('q=');
  });

  it('passes sort_by and sort_order when provided', async () => {
    mockFetch(200, { items: [] });

    await withPrincipal(handleSearchBookmarks, { query: 'test', limit: 10, offset: 0, sort_by: 'title', sort_order: 'asc' });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('sort_by=title');
    expect(url).toContain('sort_order=asc');
  });

  it('passes tags as repeated params with tag_match', async () => {
    mockFetch(200, { items: [] });

    await withPrincipal(handleSearchBookmarks, { limit: 10, offset: 0, tags: ['python', 'rust'] });

    const url = globalThis.fetch.mock.calls[0][0];
    const params = new URL(url).searchParams;
    expect(params.getAll('tags')).toEqual(['python', 'rust']);
    expect(params.get('tag_match')).toBe('all');
  });

  it('uses custom tag_match when provided', async () => {
    mockFetch(200, { items: [] });

    await withPrincipal(handleSearchBookmarks, { limit: 10, offset: 0, tags: ['python'], tag_match: 'any' });

    const url = globalThis.fetch.mock.calls[0][0];
    const params = new URL(url).searchParams;
    expect(params.get('tag_match')).toBe('any');
  });

  it('does not add tags params when tags array is empty', async () => {
    mockFetch(200, { items: [] });

    await withPrincipal(handleSearchBookmarks, { limit: 10, offset: 0, tags: [] });

    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).not.toContain('tags=');
    expect(url).not.toContain('tag_match=');
  });

  it('backward compat: message without tags/sort still works', async () => {
    const data = { items: [{ id: '1' }], has_more: false };
    mockFetch(200, data);

    const result = await withPrincipal(handleSearchBookmarks, { query: 'test', limit: 10, offset: 0 });

    expect(result).toMatchObject({ success: true, status: 200, data, authMode: 'pat' });
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain('q=test');
    expect(url).toContain('limit=10');
  });
});

describe('envelope on the session path (no cross-credential retry)', () => {
  it('surfaces a server 401 without retrying with the PAT', async () => {
    const jwt = jwtWithSub('user_x');
    mockClerkSession(jwt);
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    mockFetch(401, {});

    const result = await withPrincipal(handleGetLimits);

    expect(result).toMatchObject({ success: false, status: 401, body: {}, retryAfter: null, authMode: 'clerk' });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch.mock.calls[0][1].headers.Authorization).toBe(`Bearer ${jwt}`);
  });

  it('a PAT failure carries authMode pat in the envelope', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    mockFetch(401, { detail: 'Invalid token' });

    const result = await withPrincipal(handleGetTags);

    expect(result.authMode).toBe('pat');
    expect(result.status).toBe(401);
    expect(result.body).toEqual({ detail: 'Invalid token' });
  });

  it('passes the account_deleted terminal error body through on non-create handlers', async () => {
    mockClerkSession(jwtWithSub('user_x'));
    mockFetch(401, { detail: 'This account was deleted', error_code: 'account_deleted' });

    const result = await withPrincipal(handleGetTags);

    expect(result.success).toBe(false);
    expect(result.body.error_code).toBe('account_deleted');
    expect(result.authMode).toBe('clerk');
  });
});

describe('request-time principal binding (fail-closed)', () => {
  it('sends NOTHING when the expected owner differs from the credential now (account switched)', async () => {
    // Hydrated under account A; the credential live at send time is B.
    mockClerkSession(jwtWithSub('account_B'));
    mockFetch(201, { id: '1' });

    const result = await handleCreateBookmark({
      bookmark: { url: 'https://example.com' },
      expectedPrincipal: 'clerk:aaaaaaaaaaaaaaaa', // account A's owner tag
    });

    expect(result.principalChanged).toBe(true);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('fails closed when authenticated but the owner is unknown (undecodable sub) — null never matches null', async () => {
    mockClerkSession('not-a-decodable-jwt'); // clerk-authed, principal null
    mockFetch(200, {});

    const result = await withPrincipal(handleGetTags); // expectedPrincipal also null

    expect(result.principalChanged).toBe(true);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('fails closed when a handler omits expectedPrincipal entirely', async () => {
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    mockFetch(200, {});

    const result = await handleGetTags(); // no expectedPrincipal supplied

    expect(result.principalChanged).toBe(true);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
