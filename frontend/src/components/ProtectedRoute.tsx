import { Navigate, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { isDevMode } from '../config'
import { LoadingSpinnerPage } from './ui'
import { useAuthStatus } from '../hooks/useAuthStatus'
import { useSessionExpiryStore } from '../stores/sessionExpiryStore'

/**
 * Error display component shown when the auth provider encounters an error.
 */
function AuthErrorDisplay({ message }: { message: string }): ReactNode {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="alert-error max-w-md rounded-lg p-6 text-center">
        <h2 className="mb-2 text-lg font-semibold">
          Authentication Error
        </h2>
        <p>{message}</p>
        <button
          onClick={() => window.location.reload()}
          className="btn-danger mt-4"
        >
          Try Again
        </button>
      </div>
    </div>
  )
}

/**
 * Protected route wrapper that requires authentication (production mode).
 *
 * Two different unauthenticated states, two different behaviors (plan M3
 * step 7 — the session-expiry contract's "no navigation, ever"):
 * - ARRIVED signed-out (cold visit, or after deliberate logout): bounce to
 *   the landing page, as always.
 * - BECAME signed-out mid-use (session expired or was revoked; Clerk's
 *   background refresh flips the client signed-out even before any API 401):
 *   stay mounted — unmounting here is exactly the editor-destroying
 *   navigation the contract forbids — and raise the in-place re-auth dialog.
 */
function AuthenticatedRoute(): ReactNode {
  const { isAuthenticated, isLoading, error } = useAuthStatus()
  const markExpired = useSessionExpiryStore((state) => state.markExpired)
  const deliberateLogout = useSessionExpiryStore((state) => state.deliberateLogout)
  // Sticky "has been signed in during this mount" — render-adjust pattern,
  // so the became-signed-out decision is available in the same render.
  const [wasAuthenticated, setWasAuthenticated] = useState(isAuthenticated)
  if (isAuthenticated && !wasAuthenticated) {
    setWasAuthenticated(true)
  }

  const sessionDiedMidUse =
    !isAuthenticated && wasAuthenticated && !deliberateLogout

  useEffect(() => {
    if (sessionDiedMidUse) {
      markExpired()
    }
  }, [sessionDiedMidUse, markExpired])

  if (isLoading) {
    return <LoadingSpinnerPage label="Authenticating..." />
  }

  if (error) {
    return <AuthErrorDisplay message={error.message} />
  }

  if (!isAuthenticated && !sessionDiedMidUse) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

/**
 * Protected route wrapper that requires authentication.
 * In dev mode, all access is allowed without authentication.
 */
export function ProtectedRoute(): ReactNode {
  // In dev mode, allow all access without authentication
  if (isDevMode) {
    return <Outlet />
  }

  return <AuthenticatedRoute />
}
