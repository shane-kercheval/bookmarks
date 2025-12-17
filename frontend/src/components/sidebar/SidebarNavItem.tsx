/**
 * Individual navigation link item in the sidebar.
 */
import { NavLink } from 'react-router-dom'
import type { ReactNode } from 'react'

interface SidebarNavItemProps {
  to: string
  label: string
  isCollapsed: boolean
  onClick?: () => void
}

export function SidebarNavItem({ to, label, isCollapsed, onClick }: SidebarNavItemProps): ReactNode {
  return (
    <NavLink
      to={to}
      end
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center rounded-lg px-3 py-2 text-sm transition-colors ${
          isActive
            ? 'bg-gray-100 text-gray-900 font-medium'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
        } ${isCollapsed ? 'justify-center' : ''}`
      }
      title={isCollapsed ? label : undefined}
    >
      <span className={isCollapsed ? 'sr-only' : ''}>{label}</span>
    </NavLink>
  )
}
