/**
 * Route generation utilities for sidebar navigation.
 */

import type { SectionName } from '../../types'

/**
 * Get the route path for a tab order item based on its section.
 *
 * @param key - The tab key (e.g., "all", "all-bookmarks", "all-notes", "archived", "trash", "list:123")
 * @param section - The section the item belongs to
 */
export function getTabRoute(key: string, section: SectionName): string {
  // Built-in shared items - unified content view for all types
  if (key === 'all') return '/app/content'
  if (key === 'archived') return '/app/content/archived'
  if (key === 'trash') return '/app/content/trash'

  // Type-specific built-in items
  if (key === 'all-bookmarks') return '/app/bookmarks'
  if (key === 'all-notes') return '/app/notes'

  // Custom lists - route based on section
  if (key.startsWith('list:')) {
    const listId = key.replace('list:', '')
    // Lists in notes section go to notes route, otherwise bookmarks
    if (section === 'notes') {
      return `/app/notes/lists/${listId}`
    }
    // For shared and bookmarks sections, use bookmarks route
    // (shared lists can contain both types, but default to bookmarks view)
    return `/app/bookmarks/lists/${listId}`
  }

  // Fallback
  return '/app/bookmarks'
}
