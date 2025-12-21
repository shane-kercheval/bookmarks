/**
 * Route generation utilities for sidebar navigation.
 */

/**
 * Get the route path for a tab order item.
 */
export function getTabRoute(key: string): string {
  if (key === 'all') return '/app/bookmarks'
  if (key === 'archived') return '/app/bookmarks/archived'
  if (key === 'trash') return '/app/bookmarks/trash'
  if (key.startsWith('list:')) {
    const listId = key.replace('list:', '')
    return `/app/bookmarks/lists/${listId}`
  }
  return '/app/bookmarks'
}
