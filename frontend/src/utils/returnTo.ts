/**
 * Sanitize a post-login `returnTo` target.
 *
 * `returnTo` flows from `loginWithRedirect({ appState })` into a client-side
 * navigation after sign-in completes. Accepting an arbitrary value would be an
 * open-redirect vector, so only same-origin **relative** paths are allowed:
 * the value must start with a single `/`. Rejected as protocol-relative
 * (off-origin) absolute URLs:
 * - `//evil.com` — leading `//`
 * - `/\evil.com` (or any backslash) — browsers normalize `\` to `/`, so this is
 *   equivalent to `//evil.com`
 * Anything else falls back to the app root.
 */
export function toSafeReturnTo(value: unknown): string {
  if (
    typeof value === 'string' &&
    value.startsWith('/') &&
    !value.startsWith('//') &&
    !value.includes('\\')
  ) {
    return value
  }
  return '/'
}
