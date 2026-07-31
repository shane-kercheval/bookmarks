// The cache-ownership contract — a SECURITY boundary, single-sourced so the
// popup and options page cannot drift. User-derived local caches are keyed per
// account so a Sync Host account switch (two people on one Chrome profile, or
// one person toggling work/personal) never lets one account read or save
// another's cached data.
//
// `owner` is the opaque principal fingerprint from auth status (a hash, never
// a credential). A null owner (signed out, or authenticated-but-owner-unknown)
// yields a null key, which matches no partition — nothing is hydrated or
// persisted.
export const DRAFT_KEY = 'draft';
export const DRAFT_IMMUTABLE_KEY = 'draftImmutable';

// Every user-derived cache category. Also the exact set of pre-namespacing
// (0.4.0 and earlier) bare keys removed on first run under this scheme.
export const OWNED_KEYS = [DRAFT_KEY, DRAFT_IMMUTABLE_KEY, 'defaultTags', 'lastUsedTags'];

export function ownedKey(base, owner) {
  return owner ? `${base}:${owner}` : null;
}

// Pre-namespacing caches were stored under bare keys with no owner. They can't
// be safely attributed to any account, so on first run under the namespaced
// scheme they're removed rather than migrated — worst case a user loses one
// cached draft on upgrade; never a cross-account leak. Idempotent.
export async function migrateLegacyOwnedCaches() {
  const legacy = await chrome.storage.local.get(OWNED_KEYS);
  const present = OWNED_KEYS.filter((k) => k in legacy);
  if (present.length) await chrome.storage.local.remove(present);
}
