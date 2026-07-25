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

export async function getToken() {
  const { token } = await chrome.storage.local.get(['token']);
  if (!token) throw new Error('Not configured — open extension settings');
  return token;
}

export async function handleCreateBookmark(message) {
  const token = await getToken();
  const res = await fetchWithTimeout(`${API_URL}/bookmarks/`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-Request-Source': 'chrome-extension'
    },
    body: JSON.stringify(message.bookmark)
  });
  if (res.ok) {
    return { success: true, bookmark: await res.json() };
  }
  const body = await res.json().catch(() => null);
  const retryAfter = res.headers.get('Retry-After');
  return { success: false, status: res.status, body, retryAfter };
}

export async function handleGetTags() {
  const token = await getToken();
  const res = await fetchWithTimeout(`${API_URL}/tags/`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-Request-Source': 'chrome-extension'
    }
  });
  if (res.ok) {
    return { success: true, data: await res.json() };
  }
  return { success: false, status: res.status };
}

export async function handleGetLimits() {
  const token = await getToken();
  const res = await fetchWithTimeout(`${API_URL}/users/me/limits`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-Request-Source': 'chrome-extension'
    }
  });
  if (res.ok) {
    return { success: true, data: await res.json() };
  }
  return { success: false, status: res.status };
}

export async function handleSearchBookmarks(message) {
  const token = await getToken();
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
  const res = await fetchWithTimeout(`${API_URL}/bookmarks/?${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-Request-Source': 'chrome-extension'
    }
  });
  if (res.ok) {
    return { success: true, data: await res.json() };
  }
  return { success: false, status: res.status };
}
