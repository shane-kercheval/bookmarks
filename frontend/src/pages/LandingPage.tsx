import { useAuth0 } from '@auth0/auth0-react'
import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { isDevMode } from '../config'

/**
 * Loading spinner component shown while Auth0 is initializing.
 */
function LoadingSpinner(): ReactNode {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
    </div>
  )
}

/**
 * Landing page content shown to unauthenticated users.
 */
function LandingContent({ onLogin }: { onLogin: () => void }): ReactNode {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold text-gray-900">Bookmarks</h1>
        <p className="mb-8 text-lg text-gray-600">
          Save and organize your bookmarks
        </p>
        <button
          onClick={onLogin}
          className="rounded-lg bg-blue-600 px-6 py-3 text-lg font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Get Started
        </button>
      </div>
    </div>
  )
}

/**
 * Landing page with Auth0 authentication (production mode).
 */
function AuthenticatedLandingPage(): ReactNode {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0()

  if (isLoading) {
    return <LoadingSpinner />
  }

  // If already authenticated, redirect to bookmarks
  if (isAuthenticated) {
    return <Navigate to="/bookmarks" replace />
  }

  return <LandingContent onLogin={() => loginWithRedirect()} />
}

/**
 * Landing page component - public entry point.
 * In dev mode, redirects directly to bookmarks.
 * In production, shows login button for unauthenticated users.
 */
export function LandingPage(): ReactNode {
  // In dev mode, go straight to bookmarks
  if (isDevMode) {
    return <Navigate to="/bookmarks" replace />
  }

  return <AuthenticatedLandingPage />
}
