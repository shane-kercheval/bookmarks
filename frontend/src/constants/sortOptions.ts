/**
 * Sort options constants for bookmark views.
 *
 * Centralizes sort field definitions to prevent drift between
 * store, hooks, and UI components.
 */

/** All possible sort field types */
export type SortByOption = 'last_used_at' | 'created_at' | 'updated_at' | 'title' | 'archived_at' | 'deleted_at'
export type SortOrderOption = 'asc' | 'desc'

/** Base sort options available for all views (All Bookmarks, custom lists) */
export type BaseSortOption = 'last_used_at' | 'created_at' | 'updated_at' | 'title'
export const BASE_SORT_OPTIONS: readonly BaseSortOption[] = ['last_used_at', 'created_at', 'updated_at', 'title']

/** Sort options for Archived view (includes archived_at) */
export type ArchivedSortOption = BaseSortOption | 'archived_at'
export const ARCHIVED_SORT_OPTIONS: readonly ArchivedSortOption[] = [...BASE_SORT_OPTIONS, 'archived_at']

/** Sort options for Trash view (includes deleted_at) */
export type TrashSortOption = BaseSortOption | 'deleted_at'
export const TRASH_SORT_OPTIONS: readonly TrashSortOption[] = [...BASE_SORT_OPTIONS, 'deleted_at']

/** All possible sort options (union of all views) */
export const ALL_SORT_OPTIONS: readonly SortByOption[] = [...BASE_SORT_OPTIONS, 'archived_at', 'deleted_at']

/** Display labels for sort options */
export const SORT_LABELS: Record<SortByOption, string> = {
  last_used_at: 'Last Used',
  created_at: 'Date Added',
  updated_at: 'Date Modified',
  title: 'Title',
  archived_at: 'Archived At',
  deleted_at: 'Deleted At',
}

/** Default sort for each view type */
export const VIEW_DEFAULTS: Record<string, { sortBy: SortByOption; sortOrder: SortOrderOption }> = {
  all: { sortBy: 'last_used_at', sortOrder: 'desc' },
  archived: { sortBy: 'archived_at', sortOrder: 'desc' },
  trash: { sortBy: 'deleted_at', sortOrder: 'desc' },
}

/** Global default when no list default or view default exists */
export const GLOBAL_DEFAULT = { sortBy: 'last_used_at' as SortByOption, sortOrder: 'desc' as SortOrderOption }

/**
 * Get available sort options for a given view.
 */
export function getAvailableSortOptions(currentView: 'active' | 'archived' | 'deleted'): readonly SortByOption[] {
  switch (currentView) {
    case 'archived':
      return ARCHIVED_SORT_OPTIONS
    case 'deleted':
      return TRASH_SORT_OPTIONS
    default:
      return BASE_SORT_OPTIONS
  }
}

/**
 * Get the default sort for a view (used when no user override and no list default).
 */
export function getViewDefault(viewKey: string): { sortBy: SortByOption; sortOrder: SortOrderOption } {
  if (viewKey in VIEW_DEFAULTS) {
    return VIEW_DEFAULTS[viewKey]
  }
  // For custom lists (list:123), use global default
  return GLOBAL_DEFAULT
}
