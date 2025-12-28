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
    // Lists in notes section go to notes route
    if (section === 'notes') {
      return `/app/notes/lists/${listId}`
    }
    // Lists in bookmarks section go to bookmarks route
    if (section === 'bookmarks') {
      return `/app/bookmarks/lists/${listId}`
    }
    // Lists in shared section go to unified content route
    // (shared lists can contain both bookmarks and notes)
    return `/app/content/lists/${listId}`
  }

  // Fallback
  return '/app/bookmarks'
}
