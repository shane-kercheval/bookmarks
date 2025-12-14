/**
 * Reusable loading spinner component.
 */
import type { ReactNode } from 'react'

type SpinnerSize = 'sm' | 'md' | 'lg'

interface LoadingSpinnerProps {
  /** Size of the spinner */
  size?: SpinnerSize
  /** Additional CSS classes */
  className?: string
  /** Accessible label for screen readers */
  label?: string
}

const sizeClasses: Record<SpinnerSize, string> = {
  sm: 'spinner-sm',
  md: 'spinner-md',
  lg: 'spinner-lg',
}

/**
 * Loading spinner with accessibility support.
 */
export function LoadingSpinner({
  size = 'md',
  className = '',
  label = 'Loading...',
}: LoadingSpinnerProps): ReactNode {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className={className}
    >
      <div className={sizeClasses[size]} />
      <span className="sr-only">{label}</span>
    </div>
  )
}

/**
 * Centered loading spinner for full-page or container loading states.
 */
export function LoadingSpinnerCentered({
  size = 'md',
  label = 'Loading...',
}: Omit<LoadingSpinnerProps, 'className'>): ReactNode {
  return (
    <div className="flex justify-center py-12">
      <LoadingSpinner size={size} label={label} />
    </div>
  )
}
