/**
 * Reusable modal dialog component.
 */
import { useEffect, useRef } from 'react'
import type { ReactNode, MouseEvent } from 'react'

interface ModalProps {
  /** Whether the modal is open */
  isOpen: boolean
  /** Called when the modal should close */
  onClose: () => void
  /** Modal title */
  title: string
  /** Modal content */
  children: ReactNode
  /** Maximum width class (default: max-w-lg) */
  maxWidth?: string
}

/**
 * Modal dialog with backdrop, close button, and accessibility support.
 *
 * Features:
 * - Click outside to close
 * - Escape key to close
 * - Focus trap (focuses first input on open)
 * - Scroll lock when open
 * - ARIA attributes for accessibility
 */
export function Modal({
  isOpen,
  onClose,
  title,
  children,
  maxWidth = 'max-w-lg',
}: ModalProps): ReactNode {
  const modalRef = useRef<HTMLDivElement>(null)
  const previousActiveElement = useRef<HTMLElement | null>(null)

  // Handle escape key and focus management
  useEffect(() => {
    if (!isOpen) return

    // Store currently focused element to restore later
    previousActiveElement.current = document.activeElement as HTMLElement

    // Prevent body scroll
    document.body.style.overflow = 'hidden'

    // Focus first focusable element in modal
    const timeout = setTimeout(() => {
      const firstInput = modalRef.current?.querySelector<HTMLInputElement>(
        'input, textarea, select, button:not([aria-label="Close"])'
      )
      firstInput?.focus()
    }, 50)

    // Handle escape key
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('keydown', handleKeyDown)
      clearTimeout(timeout)

      // Restore focus to previously focused element
      if (previousActiveElement.current) {
        previousActiveElement.current.focus()
      }
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleBackdropClick = (e: MouseEvent): void => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  return (
    <div
      className="modal-backdrop"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div ref={modalRef} className={`modal-content ${maxWidth}`}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 id="modal-title" className="text-lg font-semibold text-gray-900">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="btn-icon"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4">
          {children}
        </div>
      </div>
    </div>
  )
}
