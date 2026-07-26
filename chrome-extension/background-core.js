import { createClerkClient } from '@clerk/chrome-extension/client';

// Injected at build time by build.mjs (esbuild define); vitest.config.js
// provides the same defines so unit tests run against the source module.
export const API_URL = __TIDDLY_API_URL__;
const CLERK_PUBLISHABLE_KEY = __TIDDLY_CLERK_PUBLISHABLE_KEY__;
const CLERK_SYNC_HOST = __TIDDLY_CLERK_SYNC_HOST__;
export const REQUEST_TIMEOUT_MS = 15000;

export async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeoutId);
    return res;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error('Request timed out');
    }
    throw err;
  }
}

// Session token via Clerk's documented on-demand background pattern: each
// distinct request creates a fresh client — the SDK deliberately bypasses its
// own singleton for background scope (verified in the installed package:
// `if (clerk && scope !== SCOPE.BACKGROUND) return clerk`), so re-loading per
// call is how web sign-in/sign-out stays observed. The ONLY sharing is
// in-flight coalescing: concurrent callers (a popup open fires status + limits
// + tags together) await one initialization, cleared in `finally` on success
// AND failure — never a resolved client retained across interactions, never a
// cached rejection poisoning the worker. Any client-side failure (no session,
// sync-host unreachable, init error) resolves to null so resolution falls
// through to the PAT.
let clerkInitInFlight = null;

async function getClerkSessionToken() {
  try {
    if (!clerkInitInFlight) {
      clerkInitInFlight = createClerkClient({
        publishableKey: CLERK_PUBLISHABLE_KEY,
        syncHost: CLERK_SYNC_HOST,
        background: true,
      }).finally(() => {
        clerkInitInFlight = null;
      });
    }
    const clerk = await clerkInitInFlight;
    return (await clerk.session?.getToken()) ?? null;
  } catch (err) {
    console.warn('Tiddly: Clerk session unavailable, falling back to token if configured:', err?.message ?? err);
    return null;
  }
}

// Credential resolution (plan M7 step 2, decided 2026-07-24): a live web
// session wins; the stored PAT is the fallback when no session is available.
// Fallback happens at resolution time ONLY — a server-side rejection of
// whichever credential was sent is surfaced to the caller, never silently
// retried with the other credential (that would mask misconfigurations and
// could switch which account a save lands in mid-flight).
export async function resolveAuth() {
  const sessionToken = await getClerkSessionToken();
  if (sessionToken) return { mode: 'clerk', token: sessionToken };
  const { token } = await chrome.storage.local.get(['token']);
  if (token) return { mode: 'pat', token };
  return { mode: 'none', token: null };
}

// Status for the popup/options pages: which method is active and what exists —
// never the token itself (tokens do not transit runtime messages).
export async function getAuthStatus() {
  const [sessionToken, { token }] = await Promise.all([
    getClerkSessionToken(),
    chrome.storage.local.get(['token']),
  ]);
  return {
    activeMode: sessionToken ? 'clerk' : token ? 'pat' : 'none',
    hasPat: Boolean(token),
    hasSession: Boolean(sessionToken),
  };
}

export async function getToken() {
  const { mode, token } = await resolveAuth();
  if (mode === 'none') {
    throw new Error('Not signed in — sign in at tiddly.me, or add an access token in extension settings');
  }
  return token;
}

// One authenticated-request boundary for every API handler: credentials are
// resolved exactly once per request, and failures preserve the full envelope —
// which credential was used (`authMode` — the options/error UI needs to
// distinguish a rejected PAT from a rejected session without racily
// re-resolving), the parsed backend error body (the backend's stable
// `error_code: "account_deleted"` terminal contract fires on every
// authenticated endpoint, not just create), and `Retry-After`. A server-side
// rejection is returned as-is — never retried with the other credential.
async function authedRequest(path, { method = 'GET', body } = {}) {
  const { mode, token } = await resolveAuth();
  if (mode === 'none') {
    throw new Error('Not signed in — sign in at tiddly.me, or add an access token in extension settings');
  }
  const headers = {
    'Authorization': `Bearer ${token}`,
    'X-Request-Source': 'chrome-extension',
  };
  const init = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetchWithTimeout(`${API_URL}${path}`, init);
  if (res.ok) {
    return { success: true, status: res.status, data: await res.json(), authMode: mode };
  }
  const errBody = await res.json().catch(() => null);
  return {
    success: false,
    status: res.status,
    body: errBody,
    retryAfter: res.headers.get('Retry-After'),
    authMode: mode,
  };
}

export async function handleCreateBookmark(message) {
  const result = await authedRequest('/bookmarks/', { method: 'POST', body: message.bookmark });
  if (result.success) {
    // Deliberate asymmetry with the other handlers' {data} envelope: the
    // popup's save flow predates authedRequest and consumes `bookmark`.
    return { success: true, bookmark: result.data, authMode: result.authMode };
  }
  return result;
}

export async function handleGetTags() {
  return authedRequest('/tags/');
}

export async function handleGetLimits() {
  return authedRequest('/users/me/limits');
}

export async function handleSearchBookmarks(message) {
  const params = new URLSearchParams({
    limit: String(message.limit || 10),
    offset: String(message.offset || 0),
  });
  if (message.query) {
    params.set('q', message.query);
  }
  if (message.sort_by) {
    params.set('sort_by', message.sort_by);
  }
  if (message.sort_order) {
    params.set('sort_order', message.sort_order);
  }
  if (Array.isArray(message.tags) && message.tags.length > 0) {
    for (const tag of message.tags) {
      params.append('tags', tag);
    }
    params.set('tag_match', message.tag_match || 'all');
  }
  return authedRequest(`/bookmarks/?${params}`);
}
