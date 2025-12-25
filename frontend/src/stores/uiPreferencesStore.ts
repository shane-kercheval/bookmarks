/**
 * Zustand store for local UI preferences.
 * Persists to localStorage without needing API calls.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { SortByOption, SortOrderOption } from '../constants/sortOptions'

// Re-export types for backwards compatibility
export type { SortByOption, SortOrderOption }

/** Available page size options */
export const PAGE_SIZE_OPTIONS = [10, 15, 20, 30, 50] as const
export type PageSize = typeof PAGE_SIZE_OPTIONS[number]
const DEFAULT_PAGE_SIZE: PageSize = 10

/** Per-view sort override */
export interface SortOverride {
  sortBy: SortByOption
  sortOrder: SortOrderOption
}

interface UIPreferencesState {
  /** Whether to use full width layout instead of constrained width */
  fullWidthLayout: boolean
  /** Global bookmark sort field (legacy, used as fallback) */
  bookmarkSortBy: SortByOption
  /** Global bookmark sort order (legacy, used as fallback) */
  bookmarkSortOrder: SortOrderOption
  /** Per-view sort overrides, keyed by view: "all", "archived", "trash", "list:5" */
  sortOverrides: Record<string, SortOverride>
  /** Number of bookmarks to display per page */
  pageSize: PageSize
}

interface UIPreferencesActions {
  toggleFullWidthLayout: () => void
  setFullWidthLayout: (value: boolean) => void
  /** @deprecated Use setSortOverride instead */
  setBookmarkSort: (sortBy: SortByOption, sortOrder: SortOrderOption) => void
  /** Set a sort override for a specific view */
  setSortOverride: (viewKey: string, sortBy: SortByOption, sortOrder: SortOrderOption) => void
  /** Clear the sort override for a specific view */
  clearSortOverride: (viewKey: string) => void
  /** Clear all sort overrides, reverting all views to their defaults */
  clearAllSortOverrides: () => void
  /** Get the sort override for a specific view (returns undefined if not set) */
  getSortOverride: (viewKey: string) => SortOverride | undefined
  /** Set the number of bookmarks to display per page */
  setPageSize: (size: PageSize) => void
}

type UIPreferencesStore = UIPreferencesState & UIPreferencesActions

export const useUIPreferencesStore = create<UIPreferencesStore>()(
  persist(
    (set, get) => ({
      // State
      fullWidthLayout: false,
      bookmarkSortBy: 'last_used_at',
      bookmarkSortOrder: 'desc',
      sortOverrides: {},
      pageSize: DEFAULT_PAGE_SIZE,

      // Actions
      toggleFullWidthLayout: () => {
        set((state) => ({ fullWidthLayout: !state.fullWidthLayout }))
      },

      setFullWidthLayout: (value: boolean) => {
        set({ fullWidthLayout: value })
      },

      setBookmarkSort: (sortBy: SortByOption, sortOrder: SortOrderOption) => {
        set({ bookmarkSortBy: sortBy, bookmarkSortOrder: sortOrder })
      },

      setSortOverride: (viewKey: string, sortBy: SortByOption, sortOrder: SortOrderOption) => {
        set((state) => ({
          sortOverrides: {
            ...state.sortOverrides,
            [viewKey]: { sortBy, sortOrder },
          },
        }))
      },

      clearSortOverride: (viewKey: string) => {
        set((state) => {
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { [viewKey]: _removed, ...rest } = state.sortOverrides
          return { sortOverrides: rest }
        })
      },

      clearAllSortOverrides: () => {
        set({ sortOverrides: {} })
      },

      getSortOverride: (viewKey: string) => {
        return get().sortOverrides[viewKey]
      },

      setPageSize: (size: PageSize) => {
        set({ pageSize: size })
      },
    }),
    {
      name: 'ui-preferences',
    }
  )
)
