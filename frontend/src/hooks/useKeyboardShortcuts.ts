/**
 * Hook for handling global keyboard shortcuts.
 */
import { useEffect, useCallback } from 'react'

/** Callback functions for keyboard shortcuts */
interface KeyboardShortcutHandlers {
  /** Called when 'n' is pressed (new bookmark) */
  onNewBookmark?: () => void
  /** Called when '/' is pressed (focus search) */
  onFocusSearch?: () => void
  /** Called when Escape is pressed (close modal) */
  onEscape?: () => void
  /** Called when Cmd/Ctrl + / is pressed (show shortcuts) */
  onShowShortcuts?: () => void
}

/**
 * Check if the currently focused element is an input or textarea.
 * Shortcuts should be disabled when the user is typing.
 */
function isInputFocused(): boolean {
  const activeElement = document.activeElement
  if (!activeElement) return false

  const tagName = activeElement.tagName.toUpperCase()
  return (
    tagName === 'INPUT' ||
    tagName === 'TEXTAREA' ||
    (activeElement as HTMLElement).isContentEditable
  )
}

/**
 * Hook for global keyboard shortcuts.
 *
 * Shortcuts:
 * - `n` - New bookmark (when not typing)
 * - `/` - Focus search (when not typing)
 * - `Escape` - Close modal
 * - `Cmd/Ctrl + /` - Show shortcuts dialog
 *
 * Usage:
 * ```tsx
 * useKeyboardShortcuts({
 *   onNewBookmark: () => setShowAddModal(true),
 *   onFocusSearch: () => searchInputRef.current?.focus(),
 *   onEscape: () => setShowModal(false),
 *   onShowShortcuts: () => setShowShortcutsDialog(true),
 * })
 * ```
 */
export function useKeyboardShortcuts(handlers: KeyboardShortcutHandlers): void {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      // Cmd/Ctrl + / - Show shortcuts (works even when typing)
      if ((event.metaKey || event.ctrlKey) && event.key === '/') {
        event.preventDefault()
        handlers.onShowShortcuts?.()
        return
      }

      // Escape - Close modal (works even when typing)
      if (event.key === 'Escape') {
        handlers.onEscape?.()
        return
      }

      // Skip other shortcuts if user is typing in an input
      if (isInputFocused()) {
        return
      }

      // n - New bookmark
      if (event.key === 'n' && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault()
        handlers.onNewBookmark?.()
        return
      }

      // / - Focus search
      if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault()
        handlers.onFocusSearch?.()
        return
      }
    },
    [handlers]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}
