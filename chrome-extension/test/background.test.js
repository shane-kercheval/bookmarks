// Message-listener boundary tests: sender validation (only this extension's
// own pages may drive the worker) and the GET_AUTH_STATUS contract (status
// fields only — never a token).
const { createClerkClient } = vi.hoisted(() => ({ createClerkClient: vi.fn() }));
vi.mock('@clerk/chrome-extension/client', () => ({ createClerkClient }));

async function loadListener() {
  vi.resetModules();
  await import('../background.js');
  expect(chrome.runtime.onMessage.addListener).toHaveBeenCalledTimes(1);
  return chrome.runtime.onMessage.addListener.mock.calls[0][0];
}

// Drives the listener the way Chrome does: resolves with the sendResponse
// payload for async handlers, or undefined when the listener declines
// (returns nothing — e.g. foreign sender).
function dispatch(listener, message, senderId = 'test-extension-id') {
  return new Promise((resolve) => {
    const handled = listener(message, { id: senderId }, resolve);
    if (handled !== true) resolve(undefined);
  });
}

beforeEach(() => {
  createClerkClient.mockResolvedValue({ session: null });
});

describe('sender validation', () => {
  it('ignores messages from a different extension id entirely', async () => {
    globalThis.fetch = vi.fn();
    const listener = await loadListener();

    const response = await dispatch(
      listener,
      { type: 'GET_AUTH_STATUS' },
      'some-other-extension',
    );

    expect(response).toBeUndefined();
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(createClerkClient).not.toHaveBeenCalled();
  });

  it('handles messages from its own extension id', async () => {
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    const listener = await loadListener();

    const response = await dispatch(listener, { type: 'GET_AUTH_STATUS' });

    expect(response).toEqual({ activeMode: 'pat', hasPat: true, hasSession: false });
  });
});

describe('GET_AUTH_STATUS message', () => {
  it('returns session-active status without any token material', async () => {
    createClerkClient.mockResolvedValue({
      session: { getToken: vi.fn().mockResolvedValue('sess-jwt-secret') },
    });
    chrome.storage.local.get.mockResolvedValue({ token: 'pat-secret' });
    const listener = await loadListener();

    const response = await dispatch(listener, { type: 'GET_AUTH_STATUS' });

    expect(response).toEqual({ activeMode: 'clerk', hasPat: true, hasSession: true });
    expect(JSON.stringify(response)).not.toContain('secret');
  });

  it('answers a safe signed-out default if status resolution itself fails', async () => {
    chrome.storage.local.get.mockRejectedValue(new Error('storage unavailable'));
    const listener = await loadListener();

    const response = await dispatch(listener, { type: 'GET_AUTH_STATUS' });

    expect(response).toEqual({ activeMode: 'none', hasPat: false, hasSession: false });
  });
});

describe('API message routing still works through the guarded listener', () => {
  it('routes CREATE_BOOKMARK and returns the handler result', async () => {
    chrome.storage.local.get.mockResolvedValue({ token: 'my-pat' });
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      status: 201,
      json: () => Promise.resolve({ id: '1' }),
      headers: { get: () => null },
    }));
    const listener = await loadListener();

    const response = await dispatch(listener, {
      type: 'CREATE_BOOKMARK',
      bookmark: { url: 'https://example.com' },
    });

    expect(response).toEqual({ success: true, bookmark: { id: '1' }, authMode: 'pat' });
  });

  it('converts a thrown auth error into a failure response carrying the structured authRequired flag', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    const listener = await loadListener();

    const response = await dispatch(listener, { type: 'GET_TAGS' });

    expect(response.success).toBe(false);
    expect(response.error).toContain('Not signed in');
    // The popup routes signed-out copy on this flag, never on the prose.
    expect(response.authRequired).toBe(true);
  });
});
