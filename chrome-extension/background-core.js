import { resolveAuth } from './auth.js';

// Injected at build time by build.mjs (esbuild define); vitest.config.js
// provides the same define so unit tests run against the source module.
export const API_URL = __TIDDLY_API_URL__;
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
    // authRequired is a structured contract for the popup's error routing —
    // consumers route on the flag, never on this prose (which may change).
    const err = new Error('Not signed in — sign in at tiddly.me, or add an access token in extension settings');
    err.authRequired = true;
    throw err;
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
