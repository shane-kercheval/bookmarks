/**
 * Tests for useBookmarkUrlParams hook.
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
      expect(result.current.selectedTags).toEqual([])
      expect(result.current.tagMatch).toBe('all')
      expect(result.current.sortBy).toBe('created_at')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.offset).toBe(0)
      expect(result.current.hasFilters).toBe(false)
    })

    it('parses search query from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=react%20hooks']),
      })

      expect(result.current.searchQuery).toBe('react hooks')
      expect(result.current.hasFilters).toBe(true)
    })

    it('parses single tag from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tags=javascript']),
      })

      expect(result.current.selectedTags).toEqual(['javascript'])
      expect(result.current.hasFilters).toBe(true)
    })

    it('parses multiple tags from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tags=javascript&tags=react&tags=typescript']),
      })

      expect(result.current.selectedTags).toEqual(['javascript', 'react', 'typescript'])
    })

    it('parses tag_match from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tag_match=any']),
      })

      expect(result.current.tagMatch).toBe('any')
    })

    it('parses sort_by from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?sort_by=title']),
      })

      expect(result.current.sortBy).toBe('title')
    })

    it('parses sort_order from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?sort_order=asc']),
      })

      expect(result.current.sortOrder).toBe('asc')
    })

    it('parses offset from URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?offset=50']),
      })

      expect(result.current.offset).toBe(50)
    })

    it('parses all params together', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=test&tags=js&tag_match=any&sort_by=title&sort_order=asc&offset=25']),
      })

      expect(result.current.searchQuery).toBe('test')
      expect(result.current.selectedTags).toEqual(['js'])
      expect(result.current.tagMatch).toBe('any')
      expect(result.current.sortBy).toBe('title')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.offset).toBe(25)
      expect(result.current.hasFilters).toBe(true)
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

    it('sets tags in URL', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({ tags: ['javascript', 'react'] })
      })

      expect(result.current.selectedTags).toEqual(['javascript', 'react'])
    })

    it('replaces existing tags', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tags=old']),
      })

      act(() => {
        result.current.updateParams({ tags: ['new1', 'new2'] })
      })

      expect(result.current.selectedTags).toEqual(['new1', 'new2'])
    })

    it('clears tags when empty array', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tags=javascript']),
      })

      act(() => {
        result.current.updateParams({ tags: [] })
      })

      expect(result.current.selectedTags).toEqual([])
    })

    it('sets tag_match in URL when not default', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({ tag_match: 'any' })
      })

      expect(result.current.tagMatch).toBe('any')
    })

    it('removes tag_match from URL when set to default "all"', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tag_match=any']),
      })

      act(() => {
        result.current.updateParams({ tag_match: 'all' })
      })

      expect(result.current.tagMatch).toBe('all')
    })

    it('sets sort_by in URL when not default', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({ sort_by: 'title' })
      })

      expect(result.current.sortBy).toBe('title')
    })

    it('removes sort_by from URL when set to default "created_at"', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?sort_by=title']),
      })

      act(() => {
        result.current.updateParams({ sort_by: 'created_at' })
      })

      expect(result.current.sortBy).toBe('created_at')
    })

    it('sets sort_order in URL when not default', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      act(() => {
        result.current.updateParams({ sort_order: 'asc' })
      })

      expect(result.current.sortOrder).toBe('asc')
    })

    it('removes sort_order from URL when set to default "desc"', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?sort_order=asc']),
      })

      act(() => {
        result.current.updateParams({ sort_order: 'desc' })
      })

      expect(result.current.sortOrder).toBe('desc')
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
          sort_by: 'title',
          sort_order: 'asc',
        })
      })

      expect(result.current.searchQuery).toBe('search')
      expect(result.current.sortBy).toBe('title')
      expect(result.current.sortOrder).toBe('asc')
    })

    it('preserves existing params when updating others', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=existing&sort_by=title']),
      })

      act(() => {
        result.current.updateParams({ offset: 25 })
      })

      expect(result.current.searchQuery).toBe('existing')
      expect(result.current.sortBy).toBe('title')
      expect(result.current.offset).toBe(25)
    })
  })

  describe('hasFilters', () => {
    it('returns false when no search or tags', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks']),
      })

      expect(result.current.hasFilters).toBe(false)
    })

    it('returns true when search query exists', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?q=test']),
      })

      expect(result.current.hasFilters).toBe(true)
    })

    it('returns true when tags exist', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tags=javascript']),
      })

      expect(result.current.hasFilters).toBe(true)
    })

    it('returns false when only sort/offset params exist', () => {
      const { result } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?sort_by=title&offset=50']),
      })

      expect(result.current.hasFilters).toBe(false)
    })
  })

  describe('selectedTags memoization', () => {
    it('returns same array reference when tags unchanged', () => {
      const { result, rerender } = renderHook(() => useBookmarkUrlParams(), {
        wrapper: createWrapper(['/bookmarks?tags=a&tags=b']),
      })

      const firstTags = result.current.selectedTags

      rerender()

      expect(result.current.selectedTags).toBe(firstTags)
    })
  })
})
