/**
 * Reusable error state component.
 */
import type { ReactNode } from 'react'

interface ErrorStateProps {
  /** Error message to display */
  message: string
  /** Retry button handler */
  onRetry?: () => void
  /** Custom retry button text */
  retryLabel?: string
}

/**
 * Error state display with optional retry button.
 */
export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Try Again',
}: ErrorStateProps): ReactNode {
  return (
    <div className="py-12 text-center">
      <svg
        className="mx-auto h-12 w-12 text-red-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <h3 className="mt-4 text-lg font-medium text-gray-900">Something went wrong</h3>
      <p className="mt-2 text-sm text-gray-500">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-secondary mt-4"
        >
          {retryLabel}
        </button>
      )}
    </div>
  )
}
