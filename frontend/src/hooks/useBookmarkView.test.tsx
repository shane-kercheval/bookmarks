/**
 * Tests for useBookmarkView hook.
 *
 * These tests ensure the hook correctly parses route paths to determine
 * the current view. Critical: all paths must include /app prefix.
 */
import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useBookmarkView } from './useBookmarkView'

/**
 * Wrapper that renders the hook inside the route structure.
 * This ensures useParams works correctly.
 */
function createWrapper(initialPath: string): ({ children }: { children: ReactNode }) => ReactNode {
  return function Wrapper({ children }: { children: ReactNode }): ReactNode {
    return (
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/app/bookmarks" element={children} />
          <Route path="/app/bookmarks/archived" element={children} />
          <Route path="/app/bookmarks/trash" element={children} />
          <Route path="/app/bookmarks/lists/:listId" element={children} />
          {/* Fallback for any other path */}
          <Route path="*" element={children} />
        </Routes>
      </MemoryRouter>
    )
  }
}

describe('useBookmarkView', () => {
  describe('active bookmarks (default)', () => {
    it('returns active view for /app/bookmarks', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/bookmarks'),
      })

      expect(result.current.currentView).toBe('active')
      expect(result.current.currentListId).toBeUndefined()
    })

    it('returns active view for /app/bookmarks with query params', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/bookmarks?search=test'),
      })

      expect(result.current.currentView).toBe('active')
      expect(result.current.currentListId).toBeUndefined()
    })
  })

  describe('archived bookmarks', () => {
    it('returns archived view for /app/bookmarks/archived', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/bookmarks/archived'),
      })

      expect(result.current.currentView).toBe('archived')
      expect(result.current.currentListId).toBeUndefined()
    })
  })

  describe('trash (deleted bookmarks)', () => {
    it('returns deleted view for /app/bookmarks/trash', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/bookmarks/trash'),
      })

      expect(result.current.currentView).toBe('deleted')
      expect(result.current.currentListId).toBeUndefined()
    })
  })

  describe('custom lists', () => {
    it('returns active view with listId for /app/bookmarks/lists/:listId', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/bookmarks/lists/123'),
      })

      expect(result.current.currentView).toBe('active')
      expect(result.current.currentListId).toBe(123)
    })

    it('returns undefined listId for non-numeric list ID', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/bookmarks/lists/invalid'),
      })

      expect(result.current.currentView).toBe('active')
      expect(result.current.currentListId).toBeUndefined()
    })
  })

  describe('fallback behavior', () => {
    it('returns active view for unknown paths', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/app/unknown'),
      })

      expect(result.current.currentView).toBe('active')
      expect(result.current.currentListId).toBeUndefined()
    })
  })

  // Guard against regression: paths WITHOUT /app prefix should NOT work
  // These tests document that the old paths are NOT supported by this hook
  describe('paths without /app prefix (regression guard)', () => {
    it('does NOT recognize /bookmarks/archived (missing /app)', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/bookmarks/archived'),
      })

      // Should fall through to default, not return 'archived'
      expect(result.current.currentView).toBe('active')
    })

    it('does NOT recognize /bookmarks/trash (missing /app)', () => {
      const { result } = renderHook(() => useBookmarkView(), {
        wrapper: createWrapper('/bookmarks/trash'),
      })

      // Should fall through to default, not return 'deleted'
      expect(result.current.currentView).toBe('active')
    })
  })
})
