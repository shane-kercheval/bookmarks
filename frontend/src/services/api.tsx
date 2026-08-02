import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import toast from 'react-hot-toast'
import { config, isDevMode } from '../config'
import { useSessionExpiryStore } from '../stores/sessionExpiryStore'

/**
 * Axios instance configured with the API base URL.
 * Auth interceptors are set up separately via setupAuthInterceptor.
 */
export const api = axios.create({
  baseURL: config.apiUrl,
  headers: {
    'X-Request-Source': 'web',  // Identifies requests from the web UI for source tracking
  },
})

/**
 * Axios instance for unauthenticated public endpoints (GET /public/{type}/{token}).
 *
 * Deliberately has NO auth interceptor: the shared `api` instance attaches an
 * provider token on every request, which rejected with `login_required` for a
 * logged-out visitor — so a public share page (built for logged-out visitors)
 * could never fetch through `api`. This instance just carries the base URL and
 * source header. The authed clone endpoint (POST .../save) still uses `api`,
 * since it requires a token.
 */
export const publicApi = axios.create({
  baseURL: config.apiUrl,
  headers: {
    'X-Request-Source': 'web',
  },
})

/**
 * HTTP statuses that the response interceptor below already toasts on.
 * Callers (notably AI-suggestion hooks surfacing errors via toast) should
 * short-circuit for these to avoid double-toasting. Keep in sync with the
 * interceptor branches below.
 */
export const GLOBALLY_TOASTED_STATUSES = [402, 429] as const

let refreshPromise: Promise<string | null> | null = null

/**
 * Token getter function type - provided by the Clerk context. clerk-js serves
 * a cached ~60s session token and refreshes it in the background; `skipCache`
 * forces a fresh mint (used on the one 401 retry). Resolves null when there is
 * no active session.
 */
type GetAccessTokenFn = (options?: { skipCache?: boolean }) => Promise<string | null>

/**
 * Extract the `sub` (Clerk user id) from a session JWT — for request/response
 * correlation only, NOT verification (the backend verifies). Returns null on any
 * malformed/opaque token so the cross-account guard can fail closed.
 */
function jwtSubject(token: string): string | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const pad = base64.length % 4
    const claims = JSON.parse(atob(pad ? base64 + '='.repeat(4 - pad) : base64)) as { sub?: unknown }
    return typeof claims.sub === 'string' ? claims.sub : null
  } catch {
    return null
  }
}

export interface PolicyVersions {
  privacy_policy_version: string
  terms_of_service_version: string
}

/**
 * Sets up auth interceptors on the API instance.
 * Should be called once when the Clerk context is available.
 *
 * 401 Retry Strategy (the observable contract — one retry, then the expiry path):
 * When a request fails with 401, we retry once with `skipCache: true` to force
 * a freshly-minted session token instead of the ~60s cached one — this covers
 * a token that expired in flight. If the retry also 401s (or no token can be
 * minted at all), the session itself is gone.
 *
 * Session expiry does NOT log the user out (plan M3 step 7): the request is
 * parked in the session-expiry store, the in-place re-auth dialog opens, and
 * on successful sign-in the parked request retries automatically — the save
 * the user attempted completes with nothing to redo. No navigation, no
 * queryClient.clear(); those happen only on deliberate logout.
 *
 * The shared `refreshPromise` prevents concurrent 401s from each forcing their
 * own server-side token mint - they all await the same refresh.
 *
 * Logging prefixed with [Auth] helps debug token expiration issues in production.
 *
 * A terminal `account_deleted` 401 is the exception to all of the above: the
 * account is gone, so there is nothing to refresh or re-auth into. It skips the
 * retry/park path entirely and hands off to `onAccountDeleted` (fired once, even
 * under concurrent 401s).
 *
 * Returns a cleanup that ejects both interceptors, so an effect re-run (Strict
 * Mode, a `getToken` identity change) replaces rather than stacks handlers.
 *
 * @param getAccessToken - Function to get the current session token (null = no session)
 * @param onAccountDeleted - Seam-provided terminal teardown for a deleted account
 * @param getActiveUserId - Returns the currently-active user id (null = signed out), for the cross-account guard
 */
export function setupAuthInterceptor(
  getAccessToken: GetAccessTokenFn,
  onAccountDeleted: () => void,
  getActiveUserId: () => string | null,
): () => void {
  refreshPromise = null
  // Closure-scoped (fresh per installation): terminal teardown fires once PER
  // deleted identity (keyed by the token `sub`). Concurrent 401s for one deletion
  // collapse, while a LATER, different identity's deletion in the same SPA session
  // (e.g. after a failed sign-out or a fresh sign-in) still gets handled — the
  // latch must not be global/permanent.
  const handledSubjects = new Set<string | null>()

  // Request interceptor - add auth token (production only)
  const requestInterceptorId = api.interceptors.request.use(
    async (requestConfig: InternalAxiosRequestConfig) => {
      const cfg = requestConfig as InternalAxiosRequestConfig & { _senderUserId?: string | null }
      if (!isDevMode) {
        try {
          const token = await getAccessToken()
          if (token) {
            requestConfig.headers.Authorization = `Bearer ${token}`
          }
          // Stamp the sending identity from the TOKEN actually attached (its
          // `sub`) — NOT the currently-active user, which can change during the
          // await above. The terminal-401 guard compares this against who's
          // active at response time to avoid tearing down a since-switched
          // account. Null (no/opaque token) makes the guard fail closed.
          cfg._senderUserId = token ? jwtSubject(token) : null
        } catch (error) {
          console.error('[Auth] Initial token fetch failed:', {
            error: error instanceof Error ? error.message : String(error),
            errorName: error instanceof Error ? error.name : 'unknown',
            url: requestConfig.url,
            timestamp: new Date().toISOString(),
          })
        }
      }
      return requestConfig
    },
    (error: AxiosError) => Promise.reject(error)
  )

  // Response interceptor - handle auth and rate limit errors
  const responseInterceptorId = api.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      if (error.response?.status === 401 && !isDevMode) {
        // Terminal deleted-account 401 (M8): the token is valid but its account
        // was deleted, so refresh/retry/re-auth can never succeed. Bypass the
        // expiry path entirely — hand off to the seam's teardown (once, shared
        // across concurrent 401s) and reject. Match the stable error_code, not
        // the human-readable detail.
        const errorCode = (error.response.data as { error_code?: string } | undefined)?.error_code
        if (errorCode === 'account_deleted') {
          // Cross-account guard: a deleted account's response can arrive after a
          // DIFFERENT account has become active in this browser. Running teardown
          // then would sign out and wipe the wrong (live) account, so tear down
          // only when the response's identity is still the active one (or nobody
          // is signed in). This does NOT change the browser-wide clear for the
          // active account's own deletion (see AuthProvider / utils/drafts).
          const sender = (error.config as { _senderUserId?: string | null } | undefined)?._senderUserId ?? null
          const current = getActiveUserId()
          // Fail closed: tear down only when nobody is signed in, or the response
          // provably belongs to the still-active identity. A live user with a
          // different-or-unverifiable sender is left untouched.
          if (current !== null && sender !== current) {
            return Promise.reject(error)
          }
          if (!handledSubjects.has(sender)) {
            // Run synchronously so the guard check and the destructive teardown
            // are atomic — no microtask gap in which the active identity could
            // change before teardown fires. The Set still dedups concurrent 401s
            // (each is a separate event that sees this synchronous add()). On
            // failure, un-mark so a later response for this identity can retry
            // instead of being latched off permanently.
            handledSubjects.add(sender)
            try {
              onAccountDeleted()
            } catch (err) {
              handledSubjects.delete(sender)
              console.warn(
                '[account-deletion] terminal teardown failed',
                err instanceof Error ? err.name : String(err),
              )
            }
          }
          return Promise.reject(error)
        }

        const requestConfig = error.config as (InternalAxiosRequestConfig & { _retryAuth?: boolean }) | undefined

        if (requestConfig && !requestConfig._retryAuth) {
          requestConfig._retryAuth = true
          try {
            if (!refreshPromise) {
              refreshPromise = getAccessToken({ skipCache: true }).finally(() => {
                refreshPromise = null
              })
            }
            const token = await refreshPromise
            if (token) {
              requestConfig.headers = requestConfig.headers ?? {}
              requestConfig.headers.Authorization = `Bearer ${token}`
              return api.request(requestConfig)
            }
            // null token: no session to mint from - fall through to the expiry path
          } catch (error) {
            console.error('[Auth] Token refresh failed:', {
              error: error instanceof Error ? error.message : String(error),
              errorName: error instanceof Error ? error.name : 'unknown',
              url: requestConfig.url,
              timestamp: new Date().toISOString(),
            })
            // Fall through to the expiry path below
          }
        }

        // Session expired: park the request for automatic retry after in-place
        // re-auth. Never navigate, never clear state here (plan M3 step 7).
        if (requestConfig) {
          return useSessionExpiryStore.getState().parkRequest(
            () => {
              // Re-auth minted a new session; clear the retry marker so the
              // replayed request gets one fresh 401-retry cycle of its own.
              requestConfig._retryAuth = false
              delete requestConfig.headers?.Authorization
              return api.request(requestConfig)
            },
            error,
          )
        }
      }
      if (error.response?.status === 402) {
        // Quota exceeded - show resource-specific message with pricing link
        const data = error.response.data as { resource?: string; limit?: number; error_code?: string }
        if (data?.error_code === 'QUOTA_EXCEEDED') {
          const resource = data.resource ?? 'item'
          const limit = data.limit ?? 0
          toast.error(
            <span>
              You've reached the limit of {limit.toLocaleString()} {resource}s.{' '}
              <a href="/pricing" className="underline font-medium">Manage your plan</a>
            </span>,
            { id: 'quota-exceeded' }
          )
        }
      }
      if (error.response?.status === 429) {
        // Two distinct 429 flavors:
        //   (1) Tiddly rate limiter — tier-bucket exhausted, pricing upsell is relevant.
        //       Sets `Retry-After`; no `error_code`.
        //   (2) Upstream LLM provider rate limit — `error_code: llm_rate_limited`,
        //       no `Retry-After`. Pricing link would mislead (user's plan is fine;
        //       it's the provider that's busy), so show provider-busy copy instead.
        const data = error.response.data as { error_code?: string }
        if (data?.error_code === 'llm_rate_limited') {
          toast.error(
            'The AI provider is busy right now. Please try again in a moment.',
            { id: 'rate-limit' }
          )
        } else {
          const retryAfter = error.response.headers['retry-after']
          const waitText = retryAfter
            ? `Please wait ${retryAfter} seconds.`
            : 'Please try again later.'
          toast.error(
            <span>
              Too many requests. {waitText}{' '}
              <a href="/pricing" className="underline font-medium">Higher limits available</a>
            </span>,
            { id: 'rate-limit' }
          )
        }
      }
      return Promise.reject(error)
    }
  )

  // Eject both interceptors on teardown so an effect re-run replaces rather
  // than stacks handlers (which would fire teardown/refresh multiple times).
  return () => {
    api.interceptors.request.eject(requestInterceptorId)
    api.interceptors.response.eject(responseInterceptorId)
  }
}

/**
 * Get current policy versions (public endpoint, no auth required).
 * Used by public pages to display version dates.
 */
export async function getPolicyVersions(): Promise<PolicyVersions> {
  // Use axios directly instead of api instance to avoid auth interceptors
  const response = await axios.get<PolicyVersions>(`${config.apiUrl}/consent/versions`)
  return response.data
}
