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
  variant?: 'default' | 'blue' | 'amber' | 'purple'
}

const activeStyles = {
  default: 'bg-gray-200 text-gray-900 font-medium',
  blue: 'bg-blue-100 text-gray-900 font-medium',
  amber: 'bg-amber-100 text-gray-900 font-medium',
  purple: 'bg-purple-100 text-gray-900 font-medium',
}

const hoverStyles = {
  default: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
  blue: 'text-gray-600 hover:bg-blue-50 hover:text-gray-900',
  amber: 'text-gray-600 hover:bg-amber-50 hover:text-gray-900',
  purple: 'text-gray-600 hover:bg-purple-50 hover:text-gray-900',
}

export function SidebarNavItem({
  to,
  label,
  isCollapsed,
  onClick,
  variant = 'default',
}: SidebarNavItemProps): ReactNode {
  return (
    <NavLink
      to={to}
      end
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center rounded-lg px-3 py-2 text-sm transition-colors ${
          isActive ? activeStyles[variant] : hoverStyles[variant]
        } ${isCollapsed ? 'justify-center' : ''}`
      }
      title={isCollapsed ? label : undefined}
    >
      <span className={isCollapsed ? 'sr-only' : ''}>{label}</span>
    </NavLink>
  )
}
