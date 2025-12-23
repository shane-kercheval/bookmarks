/**
 * Tests for useBookmarkUrlParams hook.
 *
 * Note: Tag filters are managed by useTagFilterStore for persistence across navigation.
 * Sort preferences are managed by useEffectiveSort for per-view persistence.
 * This hook only manages search and pagination.
 */
import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useBookmarkUrlParams } from './useBookmarkUrlParams'

describe('useBookmarkUrlParams', () => {
  const createWrapper = (initialEntries: string[] = ['/']) => {
    return function Wrapper({ children }: { children: ReactNode }) {
      return (
        <MemoryRouter initialEntries={initialEntries}>
          {children}
        </MemoryRouter>
      )
    }
  }

  describe('parsing', () => {
    it('returns default values when no URL params', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      expect(result.current.searchQuery).toBe('')
      expect(result.current.offset).toBe(0)
    })

    it('parses search query from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=react%20hooks']),
      })

      expect(result.current.searchQuery).toBe('react hooks')
    })

    it('parses offset from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?offset=50']),
      })

      expect(result.current.offset).toBe(50)
    })

    it('parses all params together', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=test&offset=25']),
      })

      expect(result.current.searchQuery).toBe('test')
      expect(result.current.offset).toBe(25)
    })
  })

  describe('updateParams', () => {
    it('sets search query in URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({ q: 'react hooks' })
      })

      expect(result.current.searchQuery).toBe('react hooks')
    })

    it('removes search query from URL when empty', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=test']),
      })

      act(() => {
        result.current.updateParams({ q: '' })
      })

      expect(result.current.searchQuery).toBe('')
    })

    it('sets offset in URL when not zero', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({ offset: 50 })
      })

      expect(result.current.offset).toBe(50)
    })

    it('removes offset from URL when set to zero', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?offset=50']),
      })

      act(() => {
        result.current.updateParams({ offset: 0 })
      })

      expect(result.current.offset).toBe(0)
    })

    it('updates multiple params at once', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({
          q: 'search',
          offset: 25,
        })
      })

      expect(result.current.searchQuery).toBe('search')
      expect(result.current.offset).toBe(25)
    })

    it('preserves existing params when updating others', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=existing']),
      })

      act(() => {
        result.current.updateParams({ offset: 25 })
      })

      expect(result.current.searchQuery).toBe('existing')
      expect(result.current.offset).toBe(25)
    })
  })
})
