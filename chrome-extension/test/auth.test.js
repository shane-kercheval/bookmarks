// Credential-resolution tests: session-wins precedence, in-flight coalescing
// of the full token resolution, and the storage.session render snapshot.
//
// The module holds real state (the in-flight resolution promise), so every
// test imports a fresh module graph — isolation comes from resetModules, not
// from test-only reset hooks in production code.
const { createClerkClient } = vi.hoisted(() => ({ createClerkClient: vi.fn() }));
vi.mock('@clerk/chrome-extension/client', () => ({ createClerkClient }));

let resolveAuth, getAuthStatus;

// Returns the session's getToken spy (null when signed out) so tests can
// assert coalescing covers the WHOLE resolution — client creation and token
// fetch — not just client creation.
function mockClerkSession(token) {
  const getToken = token === null ? null : vi.fn().mockResolvedValue(token);
  createClerkClient.mockResolvedValue({
    session: getToken ? { getToken } : null,
  });
  return getToken;
}

beforeEach(async () => {
  createClerkClient.mockReset();
  mockClerkSession(null);
  vi.resetModules();
  ({ resolveAuth, getAuthStatus } = await import('../auth.js'));
});

describe('resolution precedence (session wins; PAT is the fallback)', () => {
  it('uses the session token even when a PAT is configured', async () => {
    mockClerkSession('sess-jwt');
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toEqual({ mode: 'clerk', token: 'sess-jwt' });
  });

  it('falls back to the PAT when there is no live session', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toEqual({ mode: 'pat', token: 'my-pat' });
  });

  it('falls back to the PAT when Clerk client creation fails', async () => {
    createClerkClient.mockRejectedValue(new Error('sync host unreachable'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toEqual({ mode: 'pat', token: 'my-pat' });
  });

  it('falls back to the PAT when the session token fetch fails', async () => {
    createClerkClient.mockResolvedValue({
      session: { getToken: vi.fn().mockRejectedValue(new Error('token refresh failed')) },
    });
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toEqual({ mode: 'pat', token: 'my-pat' });
  });

  it('reports none when nothing is configured', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({});

    await expect(resolveAuth()).resolves.toEqual({ mode: 'none', token: null });
  });

  it('a failed Clerk call never poisons a later one (worker-lifetime resilience)', async () => {
    createClerkClient.mockRejectedValueOnce(new Error('transient failure'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    await expect(resolveAuth()).resolves.toEqual({ mode: 'pat', token: 'my-pat' });

    mockClerkSession('sess-jwt');
    await expect(resolveAuth()).resolves.toEqual({ mode: 'clerk', token: 'sess-jwt' });
  });
});

describe('in-flight coalescing (no resolved-token reuse across interactions)', () => {
  // THE regression from the withdrawn 45s cache (review round 2026-07-26):
  // an account switch on the web must take effect on the very next
  // interaction — no window where the extension keeps acting as the
  // previous account.
  it('account switch on the web is observed by the next sequential resolution', async () => {
    mockClerkSession('token-account-a');
    await expect(resolveAuth()).resolves.toEqual({ mode: 'clerk', token: 'token-account-a' });

    mockClerkSession('token-account-b'); // A signed out, B signed in
    await expect(resolveAuth()).resolves.toEqual({ mode: 'clerk', token: 'token-account-b' });
  });

  it('a concurrent burst shares ONE full resolution — one client init and one token fetch', async () => {
    const getToken = mockClerkSession('sess-jwt');

    const [a, b, c] = await Promise.all([resolveAuth(), resolveAuth(), resolveAuth()]);

    expect(a.token).toBe('sess-jwt');
    expect(b.token).toBe('sess-jwt');
    expect(c.token).toBe('sess-jwt');
    expect(createClerkClient).toHaveBeenCalledTimes(1);
    expect(getToken).toHaveBeenCalledTimes(1);
  });

  it('sequential interactions each resolve fresh (sign-out observed immediately)', async () => {
    mockClerkSession('sess-jwt');
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    await resolveAuth();

    mockClerkSession(null); // signed out on the web
    await expect(resolveAuth()).resolves.toEqual({ mode: 'pat', token: 'my-pat' });
    expect(createClerkClient).toHaveBeenCalledTimes(2);
  });

  it('a shared in-flight rejection falls back cleanly for every concurrent caller', async () => {
    createClerkClient.mockRejectedValue(new Error('sync host unreachable'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    const [a, b] = await Promise.all([resolveAuth(), resolveAuth()]);

    expect(a).toEqual({ mode: 'pat', token: 'my-pat' });
    expect(b).toEqual({ mode: 'pat', token: 'my-pat' });
    expect(createClerkClient).toHaveBeenCalledTimes(1);
  });

  it('resolves fresh after a worker restart (module state rebuilt)', async () => {
    mockClerkSession('sess-jwt');
    await resolveAuth();

    vi.resetModules();
    const fresh = await import('../auth.js');
    mockClerkSession('sess-jwt-after-restart');

    await expect(fresh.resolveAuth()).resolves.toEqual({ mode: 'clerk', token: 'sess-jwt-after-restart' });
  });
});

describe('getAuthStatus (status only — never a token) + render snapshot', () => {
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

  it('persists the snapshot to storage.session with mode flags only', async () => {
    mockClerkSession('sess-jwt');
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await getAuthStatus();

    expect(chrome.storage.session.set).toHaveBeenCalledWith({
      authSnapshot: { activeMode: 'clerk', hasPat: true, hasSession: true },
    });
    const written = JSON.stringify(chrome.storage.session.set.mock.calls);
    expect(written).not.toContain('sess-jwt');
    expect(written).not.toContain('my-pat');
  });

  it('still returns status when the snapshot write fails', async () => {
    chrome.storage.session.set.mockRejectedValue(new Error('storage full'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(getAuthStatus()).resolves.toEqual({
      activeMode: 'pat', hasPat: true, hasSession: false,
    });
  });
});
