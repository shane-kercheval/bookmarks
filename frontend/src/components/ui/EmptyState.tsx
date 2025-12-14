/**
 * Reusable empty state component.
 */
import type { ReactNode } from 'react'

interface EmptyStateProps {
  /** Icon to display (SVG element) */
  icon: ReactNode
  /** Main heading */
  title: string
  /** Description text */
  description: string
  /** Optional action button */
  action?: {
    label: string
    onClick: () => void
  }
}

/**
 * Empty state display for when there's no data to show.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: EmptyStateProps): ReactNode {
  return (
    <div className="py-12 text-center">
      <div className="mx-auto h-12 w-12 text-gray-400">
        {icon}
      </div>
      <h3 className="mt-4 text-lg font-medium text-gray-900">{title}</h3>
      <p className="mt-2 text-sm text-gray-500">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="btn-primary mt-4"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
