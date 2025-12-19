/**
 * User info and logout section at the bottom of the sidebar.
 */
import { useAuth0 } from '@auth0/auth0-react'
import type { ReactNode } from 'react'
import { isDevMode } from '../../config'

interface SidebarUserSectionProps {
  isCollapsed: boolean
}

function UserIcon(): ReactNode {
  return (
    <svg
      className="h-5 w-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"
      />
    </svg>
  )
}

function LogoutIcon(): ReactNode {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9"
      />
    </svg>
  )
}

export function SidebarUserSection({ isCollapsed }: SidebarUserSectionProps): ReactNode {
  const { user, logout } = useAuth0()

  const handleLogout = (): void => {
    logout({ logoutParams: { returnTo: window.location.origin } })
  }

  if (isDevMode) {
    return (
      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2 ${
          isCollapsed ? 'justify-center' : ''
        }`}
        title={isCollapsed ? 'Dev User' : undefined}
      >
        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-yellow-100 text-yellow-800">
          <UserIcon />
        </span>
        {!isCollapsed && (
          <span className="text-sm font-medium text-yellow-800">Dev User</span>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      {/* User info */}
      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2 ${
          isCollapsed ? 'justify-center' : ''
        }`}
        title={isCollapsed ? user?.email : undefined}
      >
        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-600">
          <UserIcon />
        </span>
        {!isCollapsed && (
          <span className="truncate text-sm text-gray-600">{user?.email}</span>
        )}
      </div>
      {/* Logout button */}
      <button
        onClick={handleLogout}
        className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700 ${
          isCollapsed ? 'justify-center' : ''
        }`}
        title="Log out"
      >
        <LogoutIcon />
        {!isCollapsed && <span>Log out</span>}
      </button>
    </div>
  )
}
