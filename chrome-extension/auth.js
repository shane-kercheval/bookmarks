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
  try {
    await chrome.storage.session.set({ authSnapshot: status });
  } catch {
    // Snapshot is an optimization only — status still returns.
  }
  return status;
}
