/**
 * Reusable modal dialog component.
 */
import { useEffect, useRef } from 'react'
import type { ReactNode, MouseEvent } from 'react'
import { CloseIcon } from '../icons'

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
  /** Whether to remove content padding (default: false) */
  noPadding?: boolean
  /** Whether the modal can be closed via escape/backdrop (default: true) */
  canClose?: boolean
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
  noPadding = false,
  canClose = true,
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

    // Focus first focusable element in modal using requestAnimationFrame
    // for more reliable timing than setTimeout
    let animationFrameId: number | null = null
    animationFrameId = requestAnimationFrame(() => {
      const firstInput = modalRef.current?.querySelector<HTMLInputElement>(
        'input, textarea, select, button:not([aria-label="Close"])'
      )
      firstInput?.focus()
    })

    // Handle escape key
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape' && canClose) {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('keydown', handleKeyDown)
      if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId)
      }

      // Restore focus to previously focused element
      if (previousActiveElement.current) {
        previousActiveElement.current.focus()
      }
    }
  }, [isOpen, onClose, canClose])

  if (!isOpen) return null

  const handleBackdropClick = (e: MouseEvent): void => {
    if (e.target === e.currentTarget && canClose) {
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
            disabled={!canClose}
            className="btn-icon"
            aria-label="Close"
          >
            <CloseIcon />
          </button>
        </div>

        {/* Content */}
        <div className={noPadding ? '' : 'px-6 py-4'}>
          {children}
        </div>
      </div>
    </div>
  )
}
