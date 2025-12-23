/**
 * Hook to resolve the effective sort order for a bookmark view.
 *
 * Implements the sort priority chain:
 * 1. User override (stored in localStorage via Zustand)
 * 2. List default (from BookmarkList.default_sort_by/default_sort_ascending)
 * 3. View default (hardcoded per view type)
 * 4. Global default (last_used_at desc)
 */
import { useCallback, useMemo } from 'react'

import type { SortByOption, SortOrderOption } from '../constants/sortOptions'
import { GLOBAL_DEFAULT, getAvailableSortOptions, getViewDefault } from '../constants/sortOptions'
import { useUIPreferencesStore } from '../stores/uiPreferencesStore'

export interface ListSortDefault {
  sortBy?: string | null
  ascending?: boolean | null
}

export interface UseEffectiveSortResult {
  /** The resolved sort field */
  sortBy: SortByOption
  /** The resolved sort order */
  sortOrder: SortOrderOption
  /** Set a user override for the current view */
  setSort: (sortBy: SortByOption, sortOrder: SortOrderOption) => void
  /** True if the current sort is a user override (not using list/view default) */
  isOverridden: boolean
  /** Clear the user override for the current view */
  clearOverride: () => void
  /** Available sort options for the current view (context-aware) */
  availableSortOptions: readonly SortByOption[]
}

/**
 * Derive the view key from the current view and list ID.
 */
export function getViewKey(currentView: 'active' | 'archived' | 'deleted', listId?: number | null): string {
  if (listId != null) {
    return `list:${listId}`
  }
  switch (currentView) {
    case 'archived':
      return 'archived'
    case 'deleted':
      return 'trash'
    default:
      return 'all'
  }
}

/**
 * Hook to resolve the effective sort for a bookmark view.
 *
 * @param viewKey - The view identifier ("all", "archived", "trash", "list:123")
 * @param currentView - The current view type ("active", "archived", "deleted")
 * @param listDefault - Optional list default sort configuration
 */
export function useEffectiveSort(
  viewKey: string,
  currentView: 'active' | 'archived' | 'deleted',
  listDefault?: ListSortDefault
): UseEffectiveSortResult {
  const sortOverrides = useUIPreferencesStore((state) => state.sortOverrides)
  const setSortOverride = useUIPreferencesStore((state) => state.setSortOverride)
  const clearSortOverrideAction = useUIPreferencesStore((state) => state.clearSortOverride)

  // Get the user override for this view (if any)
  const userOverride = sortOverrides[viewKey]

  // Available sort options depend on the view type
  const availableSortOptions = useMemo(() => getAvailableSortOptions(currentView), [currentView])

  // Resolve the effective sort using the priority chain
  const { sortBy, sortOrder, isOverridden } = useMemo(() => {
    // Priority 1: User override
    if (userOverride) {
      return {
        sortBy: userOverride.sortBy,
        sortOrder: userOverride.sortOrder,
        isOverridden: true,
      }
    }

    // Priority 2: List default (only for custom lists)
    if (listDefault?.sortBy) {
      const ascending = listDefault.ascending ?? false
      return {
        sortBy: listDefault.sortBy as SortByOption,
        sortOrder: (ascending ? 'asc' : 'desc') as SortOrderOption,
        isOverridden: false,
      }
    }

    // Priority 3: View default (for built-in views)
    const viewDefault = getViewDefault(viewKey)
    if (viewDefault !== GLOBAL_DEFAULT) {
      return {
        ...viewDefault,
        isOverridden: false,
      }
    }

    // Priority 4: Global default
    return {
      ...GLOBAL_DEFAULT,
      isOverridden: false,
    }
  }, [userOverride, listDefault, viewKey])

  // Set a user override
  const setSort = useCallback(
    (newSortBy: SortByOption, newSortOrder: SortOrderOption) => {
      setSortOverride(viewKey, newSortBy, newSortOrder)
    },
    [viewKey, setSortOverride]
  )

  // Clear the user override
  const clearOverride = useCallback(() => {
    clearSortOverrideAction(viewKey)
  }, [viewKey, clearSortOverrideAction])

  return {
    sortBy,
    sortOrder,
    setSort,
    isOverridden,
    clearOverride,
    availableSortOptions,
  }
}
