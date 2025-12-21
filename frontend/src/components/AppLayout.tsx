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
  const { needsConsent, isLoading, checkConsent } = useConsentStore()

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

  // Show loading state while checking consent
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

  // Show consent dialog if user needs to consent - don't render app until consented
  if (needsConsent === true) {
    return <ConsentDialog />
  }

  return <Outlet />
}
