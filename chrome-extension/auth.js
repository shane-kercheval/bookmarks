// Background-worker auth: Clerk session acquisition, credential resolution,
// status reporting, and the popup's render snapshot. Extracted from
// background-core.js because auth owns real state — the in-flight resolution
// promise and snapshot writes — that the request layer shouldn't absorb.
import { createClerkClient } from '@clerk/chrome-extension/client';

// Injected at build time by build.mjs (esbuild define); vitest.config.js
// provides the same defines so unit tests run against the source module.
const CLERK_PUBLISHABLE_KEY = __TIDDLY_CLERK_PUBLISHABLE_KEY__;
const CLERK_SYNC_HOST = __TIDDLY_CLERK_SYNC_HOST__;

// Session token via Clerk's documented on-demand background pattern: every
// DISTINCT interaction performs a full, fresh resolution — the SDK
// deliberately bypasses its own singleton for background scope (verified in
// the installed package: `if (clerk && scope !== SCOPE.BACKGROUND) return
// clerk`), and re-resolving per interaction is what makes web sign-in,
// sign-out, and ACCOUNT SWITCHING take effect immediately. The ONLY sharing
// is in-flight coalescing of the whole resolution (client creation + token
// fetch), cleared in `finally` on success AND failure — OVERLAPPING callers
// share one resolution (e.g. a popup open's concurrent status/limits/tags
// burst), but no resolved token ever survives a settled resolution.
//
// Deliberately NOT a resolved-token cache: a 45-second wall-clock cache was
// built and withdrawn in review (2026-07-26) — in a Sync Host extension it
// kept authenticating as a previous account for the cache window after an
// account switch on the web (a cross-account data-placement hazard), and
// wall-clock age says nothing about a JWT's actual remaining validity.
//
// Any client-side failure (no session, sync-host unreachable, init error)
// resolves to null so resolution falls through to the PAT.
let tokenResolutionInFlight = null;

async function getClerkSessionToken() {
  if (!tokenResolutionInFlight) {
    tokenResolutionInFlight = (async () => {
      const clerk = await createClerkClient({
        publishableKey: CLERK_PUBLISHABLE_KEY,
        syncHost: CLERK_SYNC_HOST,
        background: true,
      });
      return (await clerk.session?.getToken()) ?? null;
    })().finally(() => {
      tokenResolutionInFlight = null;
    });
  }
  try {
    return await tokenResolutionInFlight;
  } catch (err) {
    console.warn('Tiddly: Clerk session unavailable, falling back to token if configured:', err?.message ?? err);
    return null;
  }
}

async function sha256Hex(input) {
  const bytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// The `sub` (Clerk user id) from a session JWT, without verification — this is
// used only to derive a local cache-ownership tag, never to authorize
// anything (the backend verifies the signature). Returns null on any malformed
// token so a decode failure can never masquerade as a valid owner.
function unverifiedSub(jwt) {
  try {
    const payload = jwt.split('.')[1];
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json).sub ?? null;
  } catch {
    return null;
  }
}

// An opaque, stable per-account fingerprint for OWNING local caches and for
// request-time ownership binding — never a credential, safe to store/transit.
// Clerk sessions key on the account's `sub` (stable across token refresh and
// PAT rotation); PATs key on a hash of the whole token (documented
// credential-scoped behavior — a rotated PAT reads as a new owner and simply
// starts an empty partition, a minor annoyance, not a leak). Returns null when
// authenticated-but-owner-unknown (a Clerk token whose `sub` won't decode);
// callers MUST treat a null principal on an authed request as fail-closed, not
// as "matches another null".
async function principalFor(sessionToken, patToken) {
  if (sessionToken) {
    const sub = unverifiedSub(sessionToken);
    return sub ? `clerk:${(await sha256Hex(sub)).slice(0, 16)}` : null;
  }
  if (patToken) {
    return `pat:${(await sha256Hex(patToken)).slice(0, 16)}`;
  }
  return null;
}

// Credential resolution (plan M7 step 2, decided 2026-07-24): a live web
// session wins; the stored PAT is the fallback when no session is available.
// Fallback happens at resolution time ONLY — a server-side rejection of
// whichever credential was sent is surfaced to the caller, never silently
// retried with the other credential (that would mask misconfigurations and
// could switch which account a save lands in mid-flight).
//
// `principal` is derived from the SAME resolution that produced the token, so
// the ownership check at the request boundary is atomic with the credential —
// there's no second, independently-racing identity lookup.
export async function resolveAuth() {
  const sessionToken = await getClerkSessionToken();
  if (sessionToken) {
    return { mode: 'clerk', token: sessionToken, principal: await principalFor(sessionToken, null) };
  }
  const { token } = await chrome.storage.local.get(['token']);
  if (token) return { mode: 'pat', token, principal: await principalFor(null, token) };
  return { mode: 'none', token: null, principal: null };
}

// Status for the popup/options pages: which method is active and what exists —
// never the token itself (tokens do not transit runtime messages). Every
// resolution also refreshes the popup's render snapshot in storage.session
// (mode flags only), so subsequent popup opens render instantly instead of
// waiting out a cold Clerk initialization.
export async function getAuthStatus() {
  const [sessionToken, { token }] = await Promise.all([
    getClerkSessionToken(),
    chrome.storage.local.get(['token']),
  ]);
  const status = {
    activeMode: sessionToken ? 'clerk' : token ? 'pat' : 'none',
    hasPat: Boolean(token),
    hasSession: Boolean(sessionToken),
  };
  // The snapshot is mode flags ONLY (persisted for instant shell render) —
  // the principal is deliberately excluded so sensitive content can never be
  // hydrated from a stale stored principal; it rides the LIVE response only.
  try {
    await chrome.storage.session.set({ authSnapshot: status });
  } catch {
    // Snapshot is an optimization only — status still returns.
  }
  return { ...status, principal: await principalFor(sessionToken, token) };
}
