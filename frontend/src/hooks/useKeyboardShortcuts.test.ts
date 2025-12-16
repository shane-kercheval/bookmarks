import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcuts } from './useKeyboardShortcuts'

/**
 * Helper to create a paste event with clipboard data.
 * JSDOM doesn't have ClipboardEvent, so we create a custom event.
 */
function createPasteEvent(text: string): Event {
  const event = new Event('paste', { bubbles: true, cancelable: true })
  ;(event as Event & { clipboardData: DataTransfer }).clipboardData = {
    getData: () => text,
  } as DataTransfer
  return event
}

describe('useKeyboardShortcuts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    // Clean up any focused elements
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur()
    }
  })

  describe('paste URL handling', () => {
    it('should call onPasteUrl when a valid URL is pasted outside input fields', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      document.dispatchEvent(createPasteEvent('https://example.com'))

      expect(onPasteUrl).toHaveBeenCalledWith('https://example.com')
    })

    it('should call onPasteUrl with trimmed URL', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      document.dispatchEvent(createPasteEvent('  https://example.com  '))

      expect(onPasteUrl).toHaveBeenCalledWith('https://example.com')
    })

    it('should NOT call onPasteUrl when pasted text is not a valid URL (invalid protocol)', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      // Use ftp:// protocol which isValidUrl rejects
      document.dispatchEvent(createPasteEvent('ftp://invalid.com'))

      expect(onPasteUrl).not.toHaveBeenCalled()
    })

    it('should NOT call onPasteUrl when pasted text is plain text', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      document.dispatchEvent(createPasteEvent('just some random text'))

      expect(onPasteUrl).not.toHaveBeenCalled()
    })

    it('should NOT call onPasteUrl when pasted text looks like URL but invalid', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      document.dispatchEvent(createPasteEvent('not://a-valid-url'))

      expect(onPasteUrl).not.toHaveBeenCalled()
    })

    it('should NOT call onPasteUrl when pasting inside an input field', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      // Create and focus an input
      const input = document.createElement('input')
      document.body.appendChild(input)
      input.focus()

      document.dispatchEvent(createPasteEvent('https://example.com'))

      expect(onPasteUrl).not.toHaveBeenCalled()

      // Cleanup
      document.body.removeChild(input)
    })

    it('should NOT call onPasteUrl when pasting inside a textarea', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      // Create and focus a textarea
      const textarea = document.createElement('textarea')
      document.body.appendChild(textarea)
      textarea.focus()

      document.dispatchEvent(createPasteEvent('https://example.com'))

      expect(onPasteUrl).not.toHaveBeenCalled()

      // Cleanup
      document.body.removeChild(textarea)
    })

    it('should NOT call onPasteUrl when no handler is provided', () => {
      // Should not throw
      renderHook(() => useKeyboardShortcuts({}))

      expect(() => document.dispatchEvent(createPasteEvent('https://example.com'))).not.toThrow()
    })

    it('should NOT call onPasteUrl when clipboard is empty', () => {
      const onPasteUrl = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onPasteUrl }))

      document.dispatchEvent(createPasteEvent(''))

      expect(onPasteUrl).not.toHaveBeenCalled()
    })
  })

  describe('keyboard shortcuts', () => {
    it('should call onNewBookmark when n is pressed outside input fields', () => {
      const onNewBookmark = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onNewBookmark }))

      const keyEvent = new KeyboardEvent('keydown', { key: 'n' })
      document.dispatchEvent(keyEvent)

      expect(onNewBookmark).toHaveBeenCalled()
    })

    it('should NOT call onNewBookmark when n is pressed inside an input', () => {
      const onNewBookmark = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onNewBookmark }))

      const input = document.createElement('input')
      document.body.appendChild(input)
      input.focus()

      const keyEvent = new KeyboardEvent('keydown', { key: 'n' })
      document.dispatchEvent(keyEvent)

      expect(onNewBookmark).not.toHaveBeenCalled()

      document.body.removeChild(input)
    })

    it('should call onFocusSearch when / is pressed outside input fields', () => {
      const onFocusSearch = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onFocusSearch }))

      const keyEvent = new KeyboardEvent('keydown', { key: '/' })
      document.dispatchEvent(keyEvent)

      expect(onFocusSearch).toHaveBeenCalled()
    })

    it('should call onShowShortcuts when Cmd+/ is pressed', () => {
      const onShowShortcuts = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onShowShortcuts }))

      const keyEvent = new KeyboardEvent('keydown', { key: '/', metaKey: true })
      document.dispatchEvent(keyEvent)

      expect(onShowShortcuts).toHaveBeenCalled()
    })

    it('should call onShowShortcuts when Ctrl+/ is pressed (Windows/Linux)', () => {
      const onShowShortcuts = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onShowShortcuts }))

      const keyEvent = new KeyboardEvent('keydown', { key: '/', ctrlKey: true })
      document.dispatchEvent(keyEvent)

      expect(onShowShortcuts).toHaveBeenCalled()
    })

    it('should call onEscape when Escape is pressed', () => {
      const onEscape = vi.fn()
      renderHook(() => useKeyboardShortcuts({ onEscape }))

      const keyEvent = new KeyboardEvent('keydown', { key: 'Escape' })
      document.dispatchEvent(keyEvent)

      expect(onEscape).toHaveBeenCalled()
    })
  })
})
