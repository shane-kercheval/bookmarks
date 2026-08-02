import { ClerkProvider, useAuth, useClerk, useUser } from '@clerk/clerk-react'
import { useCallback, useEffect, useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { config, isDevMode } from '../config'
import { setupAuthInterceptor } from '../services/api'
import { useAIStore } from '../stores/aiStore'
import { useSessionExpiryStore } from '../stores/sessionExpiryStore'
import { clearAllDrafts } from '../utils/drafts'
import { queryClient } from '../queryClient'
import { toSafeReturnTo } from '../utils/returnTo'
import { AuthSeamProvider } from './AuthSeamProvider'
import type { AuthActions } from '../hooks/useAuthActions'

/** Clerk may hand the router an absolute URL; compare and navigate path-relative. */
function stripOrigin(to: string): string {
  return to.startsWith(window.location.origin)
    ? to.slice(window.location.origin.length) || '/'
    : to
}

function isSameLocation(to: string): boolean {
  return stripOrigin(to) === window.location.pathname + window.location.search
}

interface AuthProviderProps {
  children: ReactNode
}

// Stable no-op actions for dev mode: the app never renders login/logout
// controls there, but the seam must still resolve everywhere.
const DEV_ACTIONS: AuthActions = {
  login: () => console.warn('[auth] login() is a no-op in dev mode'),
  logout: () => console.warn('[auth] logout() is a no-op in dev mode'),
}

const DEV_STATUS = {
  isAuthenticated: true,
  isLoading: false,
  error: null,
  userId: 'dev-user',
  userEmail: null,
} as const

// Applied to every prebuilt Clerk surface (sign-in/sign-up modals, the
// session-expiry dialog's <SignIn>, <UserProfile />): brand-align with
// Tiddly's UI (gray-900 primary actions, rounded-lg) and center modals
// vertically — Clerk's default floats them near the top, unlike our own
// dialogs (session expiry), which center.
const CLERK_APPEARANCE = {
  variables: {
    colorPrimary: '#111827', // Tailwind gray-900, matching our primary buttons
    colorText: '#111827', // gray-900 — our heading/body text color
    colorTextSecondary: '#6b7280', // gray-500 — our secondary text
    borderRadius: '0.5rem', // rounded-lg
    fontFamily: 'inherit', // use the app's font stack, not Clerk's default
  },
  elements: {
    modalBackdrop: { alignItems: 'center' },
    // Flatten the component card to match our settings cards (bordered, no
    // drop shadow) so <UserProfile /> reads as part of the page, not an embed.
    cardBox: 'shadow-none border border-gray-200',
  },
}

/**
 * Bridges the Clerk SDK onto the seam: status (isAuthenticated/loading/
 * error/userId/userEmail) and actions (login/logout). This component is the
 * only place SDK hooks are read for seam purposes — call sites consume
 * useAuthStatus()/useAuthActions() and never the SDK (lint-enforced).
 *
 * Login opens Clerk's prebuilt modal (no hosted-page redirect). Without an
 * explicit returnTo, Clerk's default post-login destination is `/`, where the
 * landing page redirects signed-in users into the app — preserving the
 * pre-Clerk "log in, land in the app" behavior. A returnTo (sanitized here,
 * where it becomes a navigation target) overrides that.
 *
 * Deliberate logout owns ALL teardown (query-cache clear,
 * session-expiry state) — the session-expiry path must never do any of it
 * (plan M3 step 7: expiry may not destroy page state).
 */
function AuthSeamProviderProd({ children }: AuthProviderProps): ReactNode {
  const { isLoaded, isSignedIn, userId } = useAuth()
  const { user } = useUser()
  const clerk = useClerk()

  const actions = useMemo<AuthActions>(
    () => ({
      login: ({ mode = 'login', returnTo } = {}) => {
        const redirect = returnTo ? { forceRedirectUrl: toSafeReturnTo(returnTo) } : {}
        if (mode === 'signup') {
          void clerk.openSignUp(redirect)
        } else {
          void clerk.openSignIn(redirect)
        }
      },
      logout: () => {
        queryClient.clear()
        useSessionExpiryStore.getState().reset()
        // AFTER reset (which clears it): tells ProtectedRoute the coming
        // signed-out transition is deliberate, so it navigates instead of
        // raising the expiry dialog.
        useSessionExpiryStore.getState().beginDeliberateLogout()
        void clerk.signOut({ redirectUrl: window.location.origin })
      },
    }),
    [clerk],
  )

  // Only a hard init failure ('error': clerk-js failed to load) blocks auth
  // and surfaces ProtectedRoute's recovery screen; 'degraded' means partially
  // operational — the app still functions, so it is deliberately not fatal.
  // isLoading must drop when errored, or the loading branch would mask the
  // error screen forever (isLoaded never becomes true on a failed init).
  const initFailed = clerk.status === 'error'

  return (
    <AuthSeamProvider
      status={{
        isAuthenticated: isSignedIn ?? false,
        isLoading: !isLoaded && !initFailed,
        error: initFailed
          ? new Error('Authentication service failed to load. Please try again.')
          : null,
        userId: userId ?? null,
        userEmail: user?.primaryEmailAddress?.emailAddress ?? null,
      }}
      actions={actions}
    >
      {children}
    </AuthSeamProvider>
  )
}

/**
 * Inner component that sets up the API interceptors once Clerk is available.
 *
 * getToken() returns clerk-js's cached ~60s session token (refreshed in the
 * background — this replaces the previous provider's refresh-token machinery; there is no
 * client-held refresh token anymore). The interceptor passes
 * `{ skipCache: true }` on its one 401 retry to force a fresh mint.
 */
function AuthInterceptorSetup({ children }: AuthProviderProps): ReactNode {
  const { getToken } = useAuth()
  const clerk = useClerk()
  const navigate = useNavigate()

  // Terminal deleted-account teardown (see services/api.tsx and its cross-account
  // guard). Marks the terminal state, clears the deleted user's persisted secrets
  // (BYOK keys) + drafts and the in-memory query/session-expiry state,
  // navigates to the terminal screen, and signs out.
  //
  // What makes the terminal screen actually reached:
  //   1. `markAccountDeleted()` is set FIRST — the unsaved-changes blocker
  //      (useUnsavedChangesWarning) reads it at nav time and lets THIS forced
  //      navigation through, so a dirty editor can't trap the user on the
  //      deleted-account page with a "discard changes?" dialog.
  //   2. Every teardown step is best-effort AND surfaced (a failure — e.g.
  //      localStorage unavailable — can neither abort the transition nor silently
  //      leave a secret behind).
  //   3. Navigation is client-side and NOT gated on sign-out (fire-and-forget,
  //      pinned to /account-deleted), so it's reached even if sign-out fails.
  //
  // Accepted limitation (see utils/drafts + the migration plan): the guard in
  // api.tsx prevents tearing down a *different, currently-active* account, but
  // localStorage is per browser — so when the active account is the one deleted,
  // this clear still removes any OTHER account's leftover local drafts/keys in the
  // same browser. Worst case is loss of local unsynced data and locally-stored
  // credentials (possibly the only copy), never a server-side/account deletion.
  const onAccountDeleted = useCallback((): void => {
    useSessionExpiryStore.getState().markAccountDeleted()
    const safe = (label: string, fn: () => void): void => {
      try {
        fn()
      } catch (err) {
        console.warn(
          `[account-deletion] teardown step "${label}" failed`,
          err instanceof Error ? err.name : String(err),
        )
      }
    }
    safe('clear-queries', () => queryClient.clear())
    safe('clear-byok-keys', () => useAIStore.getState().clearAllKeys())
    safe('clear-drafts', clearAllDrafts)
    safe('reset-session-expiry', () => useSessionExpiryStore.getState().reset())
    safe('begin-deliberate-logout', () => useSessionExpiryStore.getState().beginDeliberateLogout())
    // `replace` so Back doesn't return to the dead session.
    navigate('/account-deleted', { replace: true })
    // Fire-and-forget sign-out, pinned to the terminal page so a Clerk default
    // redirect can't bounce off it. Wrapped so neither a sync throw nor a rejected
    // promise escapes; navigation already happened above.
    safe('sign-out', () =>
      void Promise.resolve(clerk.signOut({ redirectUrl: '/account-deleted' })).catch(
        (err: unknown) =>
          console.warn(
            '[account-deletion] sign-out failed',
            err instanceof Error ? err.name : String(err),
          ),
      ),
    )
  }, [clerk, navigate])

  useEffect(() => {
    if (isDevMode) return undefined
    return setupAuthInterceptor(
      (options) => getToken(options),
      onAccountDeleted,
      () => clerk.user?.id ?? null,
    )
  }, [getToken, onAccountDeleted, clerk])

  return children
}

/**
 * Auth provider component that wraps the app with the Clerk context.
 * In dev mode, ClerkProvider is skipped and no authentication is required.
 */
export function AuthProvider({ children }: AuthProviderProps): ReactNode {
  // Called unconditionally (before the dev-mode branch) to satisfy the rules
  // of hooks; only used to wire Clerk's navigation into React Router below.
  const navigate = useNavigate()

  // In dev mode, skip Clerk entirely
  if (isDevMode) {
    return (
      <AuthSeamProvider status={DEV_STATUS} actions={DEV_ACTIONS}>
        {children}
      </AuthSeamProvider>
    )
  }

  return (
    <ClerkProvider
      publishableKey={config.clerk.publishableKey}
      appearance={CLERK_APPEARANCE}
      // Route Clerk-driven navigation through React Router so post-login
      // redirects are client-side transitions, not full page loads. A
      // same-location target is a no-op: the expiry dialog pins its post-
      // re-auth redirect to the current URL precisely so nothing moves, and
      // an actual navigate() there would needlessly trip the unsaved-changes
      // blocker (caught live in the M3 rehearsal). Note: these functions are
      // registered inside clerk-js once at initialization — changes here need
      // a full page reload, not just HMR.
      routerPush={(to: string) => {
        if (!isSameLocation(to)) navigate(stripOrigin(to))
      }}
      routerReplace={(to: string) => {
        if (!isSameLocation(to)) navigate(stripOrigin(to), { replace: true })
      }}
    >
      <AuthInterceptorSetup>
        <AuthSeamProviderProd>{children}</AuthSeamProviderProd>
      </AuthInterceptorSetup>
    </ClerkProvider>
  )
}
