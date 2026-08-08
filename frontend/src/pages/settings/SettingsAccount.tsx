/**
 * Account settings page — Clerk's <UserProfile /> mounted in-app (Settings →
 * Account), rather than linking out to the hosted Account Portal, so users
 * stay inside the app consistent with the existing settings pattern.
 *
 * New capability, not parity (migration plan M3 step 9): password change,
 * session/device management, and self-serve deletion never existed under the
 * previous provider (Auth0), which shipped no end-user account UI.
 *
 * Account deletion is live: the section's visibility is controlled Clerk-side
 * ("Allow users to delete their accounts"), and it was deliberately kept off
 * until deletion was wired end-to-end — a Clerk-side deletion without the
 * `user.deleted` webhook would orphan all of the user's data in Postgres. That
 * path now exists (webhook → identity tombstone → cascade delete →
 * auth-cache invalidation), so the setting is enabled in production. If the
 * webhook is ever removed or disabled, turn the Clerk setting off with it.
 *
 * In dev mode there is no Clerk context or account to manage; the page says so
 * instead of rendering the component.
 *
 * This file is one of the few allowed to import the Clerk SDK (see
 * eslint.config.js): it mounts prebuilt Clerk UI, which cannot be expressed
 * through the seam.
 */
import type { ReactNode } from 'react'
import { UserProfile } from '@clerk/clerk-react'
import { isDevMode } from '../../config'
import { usePageTitle } from '../../hooks/usePageTitle'

export function SettingsAccount(): ReactNode {
  usePageTitle('Settings')

  // No page header: <UserProfile /> renders its own "Account / Manage your
  // account info" heading, and duplicating it read as repetitive.
  if (isDevMode) {
    return (
      <p className="pt-3 text-sm text-yellow-700">
        Dev mode: authentication is bypassed, so there is no account to manage.
      </p>
    )
  }

  // The wrapper class scopes the cl-* CSS overrides in index.css that stretch
  // and flatten the component — Clerk's appearance element keys proved
  // unreliable for <UserProfile />, so the stable cl-* classes (Clerk's
  // documented CSS escape hatch) do the styling instead. The negative margins
  // cancel the Layout content wrapper's px-4 md:px-5 / pb-4 so the component
  // is a full-bleed pane, not a padded card like the other settings pages.
  return (
    <div className="clerk-user-profile -mx-4 md:-mx-5 -mb-4">
      <UserProfile routing="hash" />
    </div>
  )
}
