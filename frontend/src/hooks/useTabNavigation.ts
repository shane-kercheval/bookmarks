/**
 * Hook for managing tab navigation state in the bookmarks page.
 *
 * Handles:
 * - Parsing tab key from URL params
 * - Deriving view ('active' | 'archived' | 'deleted') from tab key
 * - Deriving list ID for custom list tabs
 * - Updating URL when tab changes
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSettingsStore } from '../stores/settingsStore'

export type BookmarkView = 'active' | 'archived' | 'deleted'

interface DerivedTabState {
  view: BookmarkView
  listId: number | undefined
}

/**
 * Pure function to derive view and listId from a tab key.
 * Exported for unit testing.
 */
export function deriveViewFromTabKey(tabKey: string): DerivedTabState {
  if (tabKey === 'all') {
    return { view: 'active', listId: undefined }
  }
  if (tabKey === 'archived') {
    return { view: 'archived', listId: undefined }
  }
  if (tabKey === 'trash') {
    return { view: 'deleted', listId: undefined }
  }
  if (tabKey.startsWith('list:')) {
    const listId = parseInt(tabKey.replace('list:', ''), 10)
    return { view: 'active', listId: isNaN(listId) ? undefined : listId }
  }
  // Default fallback
  return { view: 'active', listId: undefined }
}

export interface UseTabNavigationReturn {
  /** Current tab key from URL (e.g., 'all', 'archived', 'trash', 'list:5') */
  currentTabKey: string
  /** Derived view for API calls */
  currentView: BookmarkView
  /** Derived list ID for custom list tabs */
  currentListId: number | undefined
  /** Handler to change the current tab */
  handleTabChange: (tabKey: string) => void
}

/**
 * Hook for tab navigation in the bookmarks page.
 *
 * Usage:
 * ```tsx
 * const { currentTabKey, currentView, currentListId, handleTabChange } = useTabNavigation()
 *
 * // Use currentView and currentListId in API calls
 * fetchBookmarks({ view: currentView, list_id: currentListId })
 *
 * // Handle tab clicks
 * <TabBar activeTabKey={currentTabKey} onTabChange={handleTabChange} />
 * ```
 */
export function useTabNavigation(): UseTabNavigationReturn {
  const [searchParams, setSearchParams] = useSearchParams()
  const { computedTabOrder } = useSettingsStore()

  // Get tab from URL, fallback to first tab in order or 'all'
  const currentTabKey = searchParams.get('tab') ||
    (computedTabOrder.length > 0 ? computedTabOrder[0].key : 'all')

  // Derive view and listId from current tab
  const { view: currentView, listId: currentListId } = useMemo(
    () => deriveViewFromTabKey(currentTabKey),
    [currentTabKey]
  )

  // Handler for tab change - updates URL
  const handleTabChange = useCallback(
    (tabKey: string) => {
      const newParams = new URLSearchParams(searchParams)

      // Set tab (use 'all' as default, don't store in URL)
      if (tabKey && tabKey !== 'all') {
        newParams.set('tab', tabKey)
      } else {
        newParams.delete('tab')
      }

      // Reset pagination when switching tabs
      newParams.delete('offset')

      setSearchParams(newParams, { replace: true })
    },
    [searchParams, setSearchParams]
  )

  return {
    currentTabKey,
    currentView,
    currentListId,
    handleTabChange,
  }
}
