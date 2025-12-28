/**
 * Hook for handling global keyboard shortcuts.
 */
import { useEffect, useCallback } from 'react'
import { isValidUrl } from '../utils'

/** Callback functions for keyboard shortcuts */
interface KeyboardShortcutHandlers {
  /** Called when 'b' is pressed (new bookmark) */
  onNewBookmark?: () => void
  /** Called when '/' is pressed (focus search) */
  onFocusSearch?: () => void
  /** Called when Escape is pressed (close modal) */
  onEscape?: () => void
  /** Called when Cmd/Ctrl + / is pressed (show shortcuts) */
  onShowShortcuts?: () => void
  /** Called when a URL is pasted outside of input fields */
  onPasteUrl?: (url: string) => void
  /** Called when 'w' is pressed (toggle width) */
  onToggleWidth?: () => void
  /** Called when Cmd/Ctrl + b is pressed (toggle sidebar) */
  onToggleSidebar?: () => void
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
 * - `b` - New bookmark (when not typing)
 * - `/` - Focus search (when not typing)
 * - `w` - Toggle content width (when not typing)
 * - `Escape` - Close modal
 * - `Cmd/Ctrl + /` - Show shortcuts dialog
 * - `Cmd/Ctrl + \` - Toggle sidebar
 * - `Cmd/Ctrl + V` - Paste URL to create bookmark (when not in input)
 *
 * Usage:
 * ```tsx
 * useKeyboardShortcuts({
 *   onNewBookmark: () => setShowAddModal(true),
 *   onFocusSearch: () => searchInputRef.current?.focus(),
 *   onToggleWidth: () => toggleFullWidthLayout(),
 *   onToggleSidebar: () => toggleSidebar(),
 *   onEscape: () => setShowModal(false),
 *   onShowShortcuts: () => setShowShortcutsDialog(true),
 *   onPasteUrl: (url) => openModalWithUrl(url),
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

      // Cmd/Ctrl + \ - Toggle sidebar (works even when typing)
      if ((event.metaKey || event.ctrlKey) && event.key === '\\') {
        event.preventDefault()
        handlers.onToggleSidebar?.()
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

      // b - New bookmark (without modifier)
      if (event.key === 'b' && !event.metaKey && !event.ctrlKey && !event.altKey) {
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

      // w - Toggle width
      if (event.key === 'w' && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault()
        handlers.onToggleWidth?.()
        return
      }
    },
    [handlers]
  )

  const handlePaste = useCallback(
    (event: ClipboardEvent) => {
      // Skip if user is in an input field
      if (isInputFocused()) {
        return
      }

      // Skip if no paste handler
      if (!handlers.onPasteUrl) {
        return
      }

      const pastedText = event.clipboardData?.getData('text')?.trim()
      if (!pastedText) {
        return
      }

      // Check if pasted text is a valid URL
      if (isValidUrl(pastedText)) {
        event.preventDefault()
        handlers.onPasteUrl(pastedText)
      }
    },
    [handlers]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('paste', handlePaste)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('paste', handlePaste)
    }
  }, [handleKeyDown, handlePaste])
}
