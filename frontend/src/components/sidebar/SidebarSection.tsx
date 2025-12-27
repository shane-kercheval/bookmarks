/**
 * Collapsible section in the sidebar with header and children.
 */
import type { ReactNode } from 'react'

interface SidebarSectionProps {
  title: string
  icon: ReactNode
  isExpanded: boolean
  onToggle: () => void
  isCollapsed: boolean
  children: ReactNode
  /** Whether this section can be collapsed. Non-collapsible sections are always expanded. */
  collapsible?: boolean
}

function ChevronIcon({ isExpanded }: { isExpanded: boolean }): ReactNode {
  return (
    <svg
      className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  )
}

export function SidebarSection({
  title,
  icon,
  isExpanded,
  onToggle,
  isCollapsed,
  children,
  collapsible = true,
}: SidebarSectionProps): ReactNode {
  // Non-collapsible sections are always effectively expanded
  const effectivelyExpanded = !collapsible || isExpanded

  const baseClassName = `flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-700 ${
    isCollapsed ? 'justify-center' : ''
  }`

  // Use a button for collapsible sections, a div for non-collapsible (accessibility)
  const HeaderElement = collapsible ? 'button' : 'div'
  const headerProps = collapsible
    ? {
        onClick: onToggle,
        type: 'button' as const,
        className: `${baseClassName} transition-colors hover:bg-gray-50 cursor-pointer`,
      }
    : {
        className: baseClassName,
        role: 'heading' as const,
        'aria-level': 2 as const,
      }

  return (
    <div className="mb-2">
      <HeaderElement {...headerProps} title={isCollapsed ? title : undefined}>
        <span className="h-5 w-5 flex-shrink-0">{icon}</span>
        {!isCollapsed && (
          <>
            <span className="flex-1 text-left">{title}</span>
            {collapsible && <ChevronIcon isExpanded={isExpanded} />}
          </>
        )}
      </HeaderElement>
      {effectivelyExpanded && !isCollapsed && (
        <div className="ml-4 mt-1 space-y-1 border-l border-gray-200 pl-2">
          {children}
        </div>
      )}
    </div>
  )
}
