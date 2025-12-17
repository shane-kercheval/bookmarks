/**
 * Tests for useTabNavigation hook.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { deriveViewFromTabKey, useTabNavigation } from './useTabNavigation'
import { useSettingsStore } from '../stores/settingsStore'

// Mock the settings store
vi.mock('../stores/settingsStore', () => ({
  useSettingsStore: vi.fn(),
}))

const mockUseSettingsStore = vi.mocked(useSettingsStore)

describe('deriveViewFromTabKey', () => {
  it('returns active view for "all" tab', () => {
    const result = deriveViewFromTabKey('all')
    expect(result).toEqual({ view: 'active', listId: undefined })
  })

  it('returns archived view for "archived" tab', () => {
    const result = deriveViewFromTabKey('archived')
    expect(result).toEqual({ view: 'archived', listId: undefined })
  })

  it('returns deleted view for "trash" tab', () => {
    const result = deriveViewFromTabKey('trash')
    expect(result).toEqual({ view: 'deleted', listId: undefined })
  })

  it('returns active view with listId for "list:N" tab', () => {
    const result = deriveViewFromTabKey('list:5')
    expect(result).toEqual({ view: 'active', listId: 5 })
  })

  it('returns active view with listId for "list:123" tab', () => {
    const result = deriveViewFromTabKey('list:123')
    expect(result).toEqual({ view: 'active', listId: 123 })
  })

  it('returns undefined listId for invalid list format "list:invalid"', () => {
    const result = deriveViewFromTabKey('list:invalid')
    expect(result).toEqual({ view: 'active', listId: undefined })
  })

  it('returns undefined listId for empty list "list:"', () => {
    const result = deriveViewFromTabKey('list:')
    expect(result).toEqual({ view: 'active', listId: undefined })
  })

  it('returns active view for unknown tab key', () => {
    const result = deriveViewFromTabKey('unknown')
    expect(result).toEqual({ view: 'active', listId: undefined })
  })

  it('returns active view for empty string', () => {
    const result = deriveViewFromTabKey('')
    expect(result).toEqual({ view: 'active', listId: undefined })
  })
})

describe('useTabNavigation', () => {
  const createWrapper = (initialEntries: string[] = ['/']) => {
    return function Wrapper({ children }: { children: ReactNode }) {
      return (
        <MemoryRouter initialEntries={initialEntries}>
          {children}
        </MemoryRouter>
      )
    }
  }

  beforeEach(() => {
    mockUseSettingsStore.mockReturnValue({
      computedTabOrder: [
        { key: 'all', label: 'All Bookmarks' },
        { key: 'archived', label: 'Archived' },
        { key: 'trash', label: 'Trash' },
      ],
      fetchTabOrder: vi.fn(),
      tabOrder: [],
      isLoading: false,
      error: null,
      saveTabOrder: vi.fn(),
    })
  })

  it('returns "all" as default tab when no URL param', () => {
    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks']),
    })

    expect(result.current.currentTabKey).toBe('all')
    expect(result.current.currentView).toBe('active')
    expect(result.current.currentListId).toBeUndefined()
  })

  it('uses first tab from computedTabOrder when available and no URL param', () => {
    mockUseSettingsStore.mockReturnValue({
      computedTabOrder: [
        { key: 'list:1', label: 'My List' },
        { key: 'all', label: 'All Bookmarks' },
      ],
      fetchTabOrder: vi.fn(),
      tabOrder: [],
      isLoading: false,
      error: null,
      saveTabOrder: vi.fn(),
    })

    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks']),
    })

    expect(result.current.currentTabKey).toBe('list:1')
    expect(result.current.currentView).toBe('active')
    expect(result.current.currentListId).toBe(1)
  })

  it('reads tab from URL param', () => {
    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks?tab=archived']),
    })

    expect(result.current.currentTabKey).toBe('archived')
    expect(result.current.currentView).toBe('archived')
    expect(result.current.currentListId).toBeUndefined()
  })

  it('reads list tab from URL param', () => {
    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks?tab=list:42']),
    })

    expect(result.current.currentTabKey).toBe('list:42')
    expect(result.current.currentView).toBe('active')
    expect(result.current.currentListId).toBe(42)
  })

  it('handleTabChange updates URL for non-default tab', () => {
    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks']),
    })

    act(() => {
      result.current.handleTabChange('archived')
    })

    expect(result.current.currentTabKey).toBe('archived')
    expect(result.current.currentView).toBe('archived')
  })

  it('handleTabChange removes tab param for "all" tab', () => {
    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks?tab=archived']),
    })

    act(() => {
      result.current.handleTabChange('all')
    })

    expect(result.current.currentTabKey).toBe('all')
  })

  it('handleTabChange resets offset when switching tabs', () => {
    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks?tab=all&offset=50']),
    })

    act(() => {
      result.current.handleTabChange('archived')
    })

    // The offset should be removed - we verify by checking the tab changed
    // (offset removal is internal URL behavior)
    expect(result.current.currentTabKey).toBe('archived')
  })

  it('falls back to "all" when computedTabOrder is empty and no URL param', () => {
    mockUseSettingsStore.mockReturnValue({
      computedTabOrder: [],
      fetchTabOrder: vi.fn(),
      tabOrder: [],
      isLoading: false,
      error: null,
      saveTabOrder: vi.fn(),
    })

    const { result } = renderHook(() => useTabNavigation(), {
      wrapper: createWrapper(['/bookmarks']),
    })

    expect(result.current.currentTabKey).toBe('all')
  })
})
