import { useAuth0 } from '@auth0/auth0-react'
import { Navigate, Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { isDevMode } from '../config'
import { LoadingSpinner } from './ui'

/**
 * Error display component shown when Auth0 encounters an error.
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
 */
function AuthenticatedRoute(): ReactNode {
  const { isAuthenticated, isLoading, error } = useAuth0()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" label="Authenticating..." />
      </div>
    )
  }

  if (error) {
    return <AuthErrorDisplay message={error.message} />
  }

  if (!isAuthenticated) {
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
