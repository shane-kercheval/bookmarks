import { useAuth0 } from '@auth0/auth0-react'
import { Outlet, Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { isDevMode } from '../config'

/**
 * Dev mode banner shown when running without Auth0 configuration.
 */
function DevModeBanner(): ReactNode {
  return (
    <div className="bg-yellow-100 px-4 py-1 text-center text-sm text-yellow-800">
      Dev Mode - Authentication disabled
    </div>
  )
}

/**
 * User controls shown in dev mode (no authentication).
 */
function DevModeUserControls(): ReactNode {
  return (
    <span className="badge bg-yellow-100 text-yellow-800">
      Dev User
    </span>
  )
}

/**
 * User controls shown when authenticated via Auth0.
 */
function AuthenticatedUserControls(): ReactNode {
  const { user, logout } = useAuth0()

  return (
    <>
      <span className="text-sm text-gray-600">{user?.email}</span>
      <button
        onClick={() =>
          logout({ logoutParams: { returnTo: window.location.origin } })
        }
        className="btn-ghost"
      >
        Log out
      </button>
    </>
  )
}

/**
 * Header component with navigation and user controls.
 */
function Header(): ReactNode {
  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        <Link to="/bookmarks" className="text-xl font-semibold text-gray-900">
          Bookmarks
        </Link>
        <nav className="flex items-center gap-4">
          {isDevMode ? <DevModeUserControls /> : <AuthenticatedUserControls />}
        </nav>
      </div>
    </header>
  )
}

/**
 * Layout component that wraps authenticated pages.
 * Includes header with navigation and logout functionality.
 */
export function Layout(): ReactNode {
  return (
    <div className="min-h-screen bg-gray-50">
      {isDevMode && <DevModeBanner />}
      <Header />
      <main className="mx-auto max-w-7xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
