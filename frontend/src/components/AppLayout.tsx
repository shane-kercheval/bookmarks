import { useEffect, type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { useConsentStore } from '../stores/consentStore'
import { ConsentDialog } from './ConsentDialog'
import { isDevMode } from '../config'

/**
 * App container component for all authenticated app routes.
 *
 * Responsibilities:
 * - Check user consent status on mount
 * - Show consent dialog if needed (unless in dev mode)
 * - Render child routes via Outlet
 *
 * Dev mode behavior:
 * - Skips consent checking entirely (mirrors auth bypass)
 * - Allows smooth local development
 */
export function AppLayout(): ReactNode {
  const { needsConsent, isLoading, error, checkConsent } = useConsentStore()

  useEffect(() => {
    // Skip consent checking in dev mode
    if (isDevMode) {
      return
    }

    // Check consent on mount (cached for session)
    checkConsent().catch((err) => {
      console.error('Failed to check consent:', err)
    })
  }, [checkConsent])

  // In dev mode, never show consent dialog
  if (isDevMode) {
    return <Outlet />
  }

  // Show loading state while checking consent (initial check only)
  if (isLoading && needsConsent === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  // Show error state if consent check failed (with retry option)
  if (error && needsConsent === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-md p-6">
          <div className="text-red-500 mb-4">
            <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Unable to Load</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => checkConsent()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Try Again
          </button>
        </div>
      </div>
    )
  }

  // Show consent dialog if user needs to consent - don't render app until consented
  if (needsConsent === true) {
    return <ConsentDialog />
  }

  // Only render app when consent is confirmed (needsConsent === false)
  // If needsConsent is still null without error, stay in loading state
  if (needsConsent !== false) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  return <Outlet />
}
