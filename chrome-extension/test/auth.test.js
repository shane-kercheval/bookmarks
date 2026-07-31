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

// A syntactically real JWT (header.payload.signature) carrying a `sub`, so the
// principal fingerprint derives a stable value the way a real session token
// would. Only the payload is decoded (unverified) for the cache-owner tag.
function jwtWithSub(sub) {
  const b64 = (o) => btoa(JSON.stringify(o)).replace(/=+$/, '');
  return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64({ sub })}.sig`;
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

    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'clerk', token: 'sess-jwt' });
  });

  it('falls back to the PAT when there is no live session', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'pat', token: 'my-pat' });
  });

  it('falls back to the PAT when Clerk client creation fails', async () => {
    createClerkClient.mockRejectedValue(new Error('sync host unreachable'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'pat', token: 'my-pat' });
  });

  it('falls back to the PAT when the session token fetch fails', async () => {
    createClerkClient.mockResolvedValue({
      session: { getToken: vi.fn().mockRejectedValue(new Error('token refresh failed')) },
    });
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'pat', token: 'my-pat' });
  });

  it('reports none when nothing is configured', async () => {
    mockClerkSession(null);
    chrome.storage.local.get.mockResolvedValue({});

    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'none', token: null });
  });

  it('a failed Clerk call never poisons a later one (worker-lifetime resilience)', async () => {
    createClerkClient.mockRejectedValueOnce(new Error('transient failure'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'pat', token: 'my-pat' });

    mockClerkSession('sess-jwt');
    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'clerk', token: 'sess-jwt' });
  });
});

describe('in-flight coalescing (no resolved-token reuse across interactions)', () => {
  // THE regression from the withdrawn 45s cache (review round 2026-07-26):
  // an account switch on the web must take effect on the very next
  // interaction — no window where the extension keeps acting as the
  // previous account.
  it('account switch on the web is observed by the next sequential resolution', async () => {
    mockClerkSession('token-account-a');
    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'clerk', token: 'token-account-a' });

    mockClerkSession('token-account-b'); // A signed out, B signed in
    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'clerk', token: 'token-account-b' });
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
    await expect(resolveAuth()).resolves.toMatchObject({ mode: 'pat', token: 'my-pat' });
    expect(createClerkClient).toHaveBeenCalledTimes(2);
  });

  it('a shared in-flight rejection falls back cleanly for every concurrent caller', async () => {
    createClerkClient.mockRejectedValue(new Error('sync host unreachable'));
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });

    const [a, b] = await Promise.all([resolveAuth(), resolveAuth()]);

    expect(a).toMatchObject({ mode: 'pat', token: 'my-pat' });
    expect(b).toMatchObject({ mode: 'pat', token: 'my-pat' });
    expect(createClerkClient).toHaveBeenCalledTimes(1);
  });

  it('resolves fresh after a worker restart (module state rebuilt)', async () => {
    mockClerkSession('sess-jwt');
    await resolveAuth();

    vi.resetModules();
    const fresh = await import('../auth.js');
    mockClerkSession('sess-jwt-after-restart');

    await expect(fresh.resolveAuth()).resolves.toMatchObject({ mode: 'clerk', token: 'sess-jwt-after-restart' });
  });
});

describe('getAuthStatus (status flags + principal; never a token) + render snapshot', () => {
  it.each([
    ['both configured → session active', jwtWithSub('user_A'), 'bm_pat', { activeMode: 'clerk', hasPat: true, hasSession: true }, /^clerk:[0-9a-f]{16}$/],
    ['session only', jwtWithSub('user_A'), undefined, { activeMode: 'clerk', hasPat: false, hasSession: true }, /^clerk:[0-9a-f]{16}$/],
    ['PAT only', null, 'bm_pat', { activeMode: 'pat', hasPat: true, hasSession: false }, /^pat:[0-9a-f]{16}$/],
    ['neither', null, undefined, { activeMode: 'none', hasPat: false, hasSession: false }, null],
  ])('%s', async (_label, sessionToken, pat, expectedFlags, principalPattern) => {
    mockClerkSession(sessionToken);
    chrome.storage.local.get.mockResolvedValue(pat ? { token: pat } : {});

    const status = await getAuthStatus();

    expect(status).toMatchObject(expectedFlags);
    if (principalPattern) {
      expect(status.principal).toMatch(principalPattern);
    } else {
      expect(status.principal).toBeNull();
    }
    // No token material in any field — including the principal (a hash).
    const serialized = JSON.stringify(status);
    if (sessionToken) expect(serialized).not.toContain(sessionToken);
    if (pat) expect(serialized).not.toContain(pat);
  });

  it('derives the SAME clerk principal across token refreshes (keyed on sub, not the token)', async () => {
    mockClerkSession(jwtWithSub('user_stable'));
    chrome.storage.local.get.mockResolvedValue({});
    const first = (await getAuthStatus()).principal;

    // A different token string for the same account (refresh) → same principal.
    mockClerkSession(jwtWithSub('user_stable'));
    const second = (await getAuthStatus()).principal;

    expect(first).toBe(second);
  });

  it('persists the snapshot to storage.session with mode flags ONLY — never the principal', async () => {
    mockClerkSession(jwtWithSub('user_A'));
    chrome.storage.local.get.mockResolvedValue({ token: 'bm_pat' });

    await getAuthStatus();

    expect(chrome.storage.session.set).toHaveBeenCalledWith({
      authSnapshot: { activeMode: 'clerk', hasPat: true, hasSession: true },
    });
    // The principal must NOT be persisted — content hydration gates on the
    // fresh live principal, never a stored (potentially stale) one.
    const snapshotArg = chrome.storage.session.set.mock.calls[0][0].authSnapshot;
    expect('principal' in snapshotArg).toBe(false);
  });

  it('still returns status when the snapshot write fails', async () => {
    chrome.storage.session.set.mockRejectedValue(new Error('storage full'));
    chrome.storage.local.get.mockResolvedValue({ token: 'bm_pat' });

    await expect(getAuthStatus()).resolves.toMatchObject({
      activeMode: 'pat', hasPat: true, hasSession: false,
    });
  });
});
