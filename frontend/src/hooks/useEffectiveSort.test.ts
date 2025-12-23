/**
 * Tests for useEffectiveSort hook.
 *
 * Tests the sort priority chain:
 * 1. User override (stored in localStorage via Zustand)
 * 2. List default (from BookmarkList.default_sort_by/default_sort_ascending)
 * 3. View default (hardcoded per view type)
 * 4. Global default (last_used_at desc)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useEffectiveSort, getViewKey } from './useEffectiveSort'
import { useUIPreferencesStore } from '../stores/uiPreferencesStore'

describe('getViewKey', () => {
  it('returns "all" for active view without listId', () => {
    expect(getViewKey('active', null)).toBe('all')
    expect(getViewKey('active', undefined)).toBe('all')
  })

  it('returns "archived" for archived view', () => {
    expect(getViewKey('archived', null)).toBe('archived')
  })

  it('returns "trash" for deleted view', () => {
    expect(getViewKey('deleted', null)).toBe('trash')
  })

  it('returns list:id for active view with listId', () => {
    expect(getViewKey('active', 5)).toBe('list:5')
    expect(getViewKey('active', 123)).toBe('list:123')
  })
})

describe('useEffectiveSort', () => {
  beforeEach(() => {
    // Reset store state before each test
    useUIPreferencesStore.setState({
      fullWidthLayout: false,
      bookmarkSortBy: 'last_used_at',
      bookmarkSortOrder: 'desc',
      sortOverrides: {},
    })
  })

  describe('priority chain', () => {
    it('uses user override when present (priority 1)', () => {
      // Set up user override
      useUIPreferencesStore.getState().setSortOverride('all', 'title', 'asc')

      const { result } = renderHook(() =>
        useEffectiveSort('all', 'active', undefined)
      )

      expect(result.current.sortBy).toBe('title')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.isOverridden).toBe(true)
    })

    it('uses list default when no user override (priority 2)', () => {
      const listDefault = { sortBy: 'created_at', ascending: true }

      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', listDefault)
      )

      expect(result.current.sortBy).toBe('created_at')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('uses list default descending when ascending is false', () => {
      const listDefault = { sortBy: 'title', ascending: false }

      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', listDefault)
      )

      expect(result.current.sortBy).toBe('title')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('uses list default descending when ascending is null', () => {
      const listDefault = { sortBy: 'updated_at', ascending: null }

      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', listDefault)
      )

      expect(result.current.sortBy).toBe('updated_at')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('uses view default when no user override and no list default (priority 3)', () => {
      const { result: archivedResult } = renderHook(() =>
        useEffectiveSort('archived', 'archived', undefined)
      )
      expect(archivedResult.current.sortBy).toBe('archived_at')
      expect(archivedResult.current.sortOrder).toBe('desc')
      expect(archivedResult.current.isOverridden).toBe(false)

      const { result: trashResult } = renderHook(() =>
        useEffectiveSort('trash', 'deleted', undefined)
      )
      expect(trashResult.current.sortBy).toBe('deleted_at')
      expect(trashResult.current.sortOrder).toBe('desc')
      expect(trashResult.current.isOverridden).toBe(false)
    })

    it('uses global default for all bookmarks view (priority 4)', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('all', 'active', undefined)
      )

      expect(result.current.sortBy).toBe('last_used_at')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('uses global default for custom lists without list default', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', undefined)
      )

      expect(result.current.sortBy).toBe('last_used_at')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('user override takes precedence over list default', () => {
      // Set up user override
      useUIPreferencesStore.getState().setSortOverride('list:5', 'updated_at', 'asc')
      const listDefault = { sortBy: 'title', ascending: false }

      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', listDefault)
      )

      expect(result.current.sortBy).toBe('updated_at')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.isOverridden).toBe(true)
    })

    it('user override takes precedence over view default', () => {
      // Set up user override for archived view
      useUIPreferencesStore.getState().setSortOverride('archived', 'title', 'asc')

      const { result } = renderHook(() =>
        useEffectiveSort('archived', 'archived', undefined)
      )

      expect(result.current.sortBy).toBe('title')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.isOverridden).toBe(true)
    })
  })

  describe('setSort', () => {
    it('creates an override for the current view', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('all', 'active', undefined)
      )

      act(() => {
        result.current.setSort('title', 'asc')
      })

      expect(result.current.sortBy).toBe('title')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.isOverridden).toBe(true)
    })

    it('does not affect other views when setting sort', () => {
      const { result: allResult } = renderHook(() =>
        useEffectiveSort('all', 'active', undefined)
      )
      const { result: archivedResult } = renderHook(() =>
        useEffectiveSort('archived', 'archived', undefined)
      )

      act(() => {
        allResult.current.setSort('title', 'asc')
      })

      // All view should be overridden
      expect(allResult.current.sortBy).toBe('title')
      expect(allResult.current.isOverridden).toBe(true)

      // Archived view should still use default
      expect(archivedResult.current.sortBy).toBe('archived_at')
      expect(archivedResult.current.isOverridden).toBe(false)
    })
  })

  describe('clearOverride', () => {
    it('clears the override and reverts to list default', () => {
      const listDefault = { sortBy: 'created_at', ascending: true }
      useUIPreferencesStore.getState().setSortOverride('list:5', 'title', 'asc')

      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', listDefault)
      )

      expect(result.current.sortBy).toBe('title')
      expect(result.current.isOverridden).toBe(true)

      act(() => {
        result.current.clearOverride()
      })

      expect(result.current.sortBy).toBe('created_at')
      expect(result.current.sortOrder).toBe('asc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('clears the override and reverts to view default', () => {
      useUIPreferencesStore.getState().setSortOverride('archived', 'title', 'asc')

      const { result } = renderHook(() =>
        useEffectiveSort('archived', 'archived', undefined)
      )

      expect(result.current.sortBy).toBe('title')
      expect(result.current.isOverridden).toBe(true)

      act(() => {
        result.current.clearOverride()
      })

      expect(result.current.sortBy).toBe('archived_at')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.isOverridden).toBe(false)
    })

    it('clears the override and reverts to global default', () => {
      useUIPreferencesStore.getState().setSortOverride('all', 'title', 'asc')

      const { result } = renderHook(() =>
        useEffectiveSort('all', 'active', undefined)
      )

      expect(result.current.sortBy).toBe('title')
      expect(result.current.isOverridden).toBe(true)

      act(() => {
        result.current.clearOverride()
      })

      expect(result.current.sortBy).toBe('last_used_at')
      expect(result.current.sortOrder).toBe('desc')
      expect(result.current.isOverridden).toBe(false)
    })
  })

  describe('availableSortOptions', () => {
    it('returns base options for active view', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('all', 'active', undefined)
      )

      expect(result.current.availableSortOptions).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
      ])
    })

    it('returns base options plus archived_at for archived view', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('archived', 'archived', undefined)
      )

      expect(result.current.availableSortOptions).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
        'archived_at',
      ])
    })

    it('returns base options plus deleted_at for deleted view', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('trash', 'deleted', undefined)
      )

      expect(result.current.availableSortOptions).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
        'deleted_at',
      ])
    })

    it('returns base options for custom list view', () => {
      const { result } = renderHook(() =>
        useEffectiveSort('list:5', 'active', undefined)
      )

      expect(result.current.availableSortOptions).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
      ])
    })
  })
})
