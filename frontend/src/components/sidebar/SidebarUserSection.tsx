/**
 * User section at the bottom of the sidebar with logout and collapse buttons.
 */
import { useAuthActions } from '../../hooks/useAuthActions'
import type { ReactNode } from 'react'
import { isDevMode } from '../../config'
import { CollapseIcon } from '../icons'
import { Tooltip } from '../ui'

interface SidebarUserSectionProps {
  isCollapsed: boolean
  onToggleCollapse?: () => void
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

function CollapseButton({ isCollapsed, onToggleCollapse }: SidebarUserSectionProps): ReactNode {
  if (!onToggleCollapse) return null

  return (
    <Tooltip content={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} compact position="right">
      <button
        onClick={onToggleCollapse}
        className="hidden md:block p-1.5 rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
        aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <CollapseIcon className={`h-4 w-4 ${isCollapsed ? 'rotate-180' : ''}`} />
      </button>
    </Tooltip>
  )
}

export function SidebarUserSection({ isCollapsed, onToggleCollapse }: SidebarUserSectionProps): ReactNode {
  // In dev mode, show button but don't use the auth provider
  if (isDevMode) {
    const logoutButton = (
      <button
        className={`flex items-center gap-2 rounded-lg px-2 py-1 text-sm text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700 ${
          isCollapsed ? 'justify-center' : 'flex-1'
        }`}
      >
        <LogoutIcon />
        {!isCollapsed && <span>Log out</span>}
      </button>
    )

    return (
      <div className={`flex w-full ${isCollapsed ? 'flex-col items-center gap-1' : 'items-center'}`}>
        {isCollapsed ? (
          <Tooltip content="Log out" compact position="right">{logoutButton}</Tooltip>
        ) : logoutButton}
        <CollapseButton isCollapsed={isCollapsed} onToggleCollapse={onToggleCollapse} />
      </div>
    )
  }

  return <LogoutButton isCollapsed={isCollapsed} onToggleCollapse={onToggleCollapse} />
}

function LogoutButton({ isCollapsed, onToggleCollapse }: SidebarUserSectionProps): ReactNode {
  const { logout } = useAuthActions()

  const handleLogout = (): void => {
    logout()
  }

  const logoutButton = (
    <button
      onClick={handleLogout}
      className={`flex items-center gap-2 rounded-lg px-2 py-1 text-sm text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700 ${
        isCollapsed ? 'justify-center' : 'flex-1'
      }`}
    >
      <LogoutIcon />
      {!isCollapsed && <span>Log out</span>}
    </button>
  )

  return (
    <div className={`flex w-full ${isCollapsed ? 'flex-col items-center gap-1' : 'items-center'}`}>
      {isCollapsed ? (
        <Tooltip content="Log out" compact position="right">{logoutButton}</Tooltip>
      ) : logoutButton}
      <CollapseButton isCollapsed={isCollapsed} onToggleCollapse={onToggleCollapse} />
    </div>
  )
}
