/**
 * Hook for managing bookmarks - fetching, creating, updating, deleting.
 *
 * Design Decision: This hook uses local React state (useState) rather than a Zustand store.
 *
 * This is intentional because bookmark state differs from other entities (tags, lists, settings):
 * - Bookmark lists are page-specific with different filters, pagination, and sort orders per view
 * - Multiple instances of the bookmarks page may need different states simultaneously
 * - URL search params drive bookmark filtering, making global state unnecessary
 * - The data is parameterized (search, tags, sort, offset) rather than a single global list
 *
 * Compare to useTagsStore/useListsStore/useSettingsStore which are truly global app state
 * that should be shared across all components without parameters.
 *
 * See: docs/implementation_plans/2025-12-15-code-review-decisions.md (item 3.1)
 */
import { useState, useCallback, useRef } from 'react'
import axios from 'axios'
import { api } from '../services/api'
import type {
  Bookmark,
  BookmarkListItem,
  BookmarkCreate,
  BookmarkUpdate,
  BookmarkListResponse,
  BookmarkSearchParams,
  MetadataPreviewResponse,
} from '../types'

interface UseBookmarksState {
  bookmarks: BookmarkListItem[]
  total: number
  isLoading: boolean
  error: string | null
  /** Whether the initial fetch has completed (success or failure) */
  hasInitiallyLoaded: boolean
}

interface UseBookmarksReturn extends UseBookmarksState {
  fetchBookmarks: (params?: BookmarkSearchParams) => Promise<void>
  fetchBookmark: (id: number) => Promise<Bookmark>
  createBookmark: (data: BookmarkCreate) => Promise<Bookmark>
  updateBookmark: (id: number, data: BookmarkUpdate) => Promise<Bookmark>
  deleteBookmark: (id: number, permanent?: boolean) => Promise<void>
  restoreBookmark: (id: number) => Promise<Bookmark>
  archiveBookmark: (id: number) => Promise<Bookmark>
  unarchiveBookmark: (id: number) => Promise<Bookmark>
  fetchMetadata: (url: string) => Promise<MetadataPreviewResponse>
  trackBookmarkUsage: (id: number) => void
  clearError: () => void
}

/**
 * Hook for managing bookmark CRUD operations.
 *
 * Usage:
 * ```tsx
 * const { bookmarks, total, isLoading, error, fetchBookmarks, createBookmark } = useBookmarks()
 *
 * useEffect(() => {
 *   fetchBookmarks({ q: searchQuery, tags: selectedTags })
 * }, [searchQuery, selectedTags])
 * ```
 */
export function useBookmarks(): UseBookmarksReturn {
  const [state, setState] = useState<UseBookmarksState>({
    bookmarks: [],
    total: 0,
    isLoading: false,
    error: null,
    hasInitiallyLoaded: false,
  })

  // AbortController for canceling in-flight requests
  const abortControllerRef = useRef<AbortController | null>(null)

  const fetchBookmarks = useCallback(async (params: BookmarkSearchParams = {}) => {
    // Cancel any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Create new AbortController for this request
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    setState((prev) => ({ ...prev, isLoading: true, error: null }))

    try {
      // Build query string from params
      const queryParams = new URLSearchParams()

      if (params.q) {
        queryParams.set('q', params.q)
      }
      if (params.tags && params.tags.length > 0) {
        params.tags.forEach((tag) => queryParams.append('tags', tag))
      }
      if (params.tag_match) {
        queryParams.set('tag_match', params.tag_match)
      }
      if (params.sort_by) {
        queryParams.set('sort_by', params.sort_by)
      }
      if (params.sort_order) {
        queryParams.set('sort_order', params.sort_order)
      }
      if (params.offset !== undefined) {
        queryParams.set('offset', String(params.offset))
      }
      if (params.limit !== undefined) {
        queryParams.set('limit', String(params.limit))
      }
      if (params.view) {
        queryParams.set('view', params.view)
      }
      if (params.list_id !== undefined) {
        queryParams.set('list_id', String(params.list_id))
      }

      const queryString = queryParams.toString()
      const url = queryString ? `/bookmarks/?${queryString}` : '/bookmarks/'

      const response = await api.get<BookmarkListResponse>(url, {
        signal: abortController.signal,
      })

      setState({
        bookmarks: response.data.items,
        total: response.data.total,
        isLoading: false,
        error: null,
        hasInitiallyLoaded: true,
      })
    } catch (err) {
      // Ignore canceled requests - a newer request superseded this one
      if (axios.isCancel(err)) {
        return
      }

      const message = err instanceof Error ? err.message : 'Failed to fetch bookmarks'
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
        hasInitiallyLoaded: true,
      }))
    }
  }, [])

  const fetchBookmark = useCallback(async (id: number): Promise<Bookmark> => {
    const response = await api.get<Bookmark>(`/bookmarks/${id}`)
    return response.data
  }, [])

  const createBookmark = useCallback(async (data: BookmarkCreate): Promise<Bookmark> => {
    const response = await api.post<Bookmark>('/bookmarks/', data)
    return response.data
  }, [])

  const updateBookmark = useCallback(
    async (id: number, data: BookmarkUpdate): Promise<Bookmark> => {
      const response = await api.patch<Bookmark>(`/bookmarks/${id}`, data)
      return response.data
    },
    []
  )

  const deleteBookmark = useCallback(async (id: number, permanent?: boolean): Promise<void> => {
    const url = permanent ? `/bookmarks/${id}?permanent=true` : `/bookmarks/${id}`
    await api.delete(url)
  }, [])

  const restoreBookmark = useCallback(async (id: number): Promise<Bookmark> => {
    const response = await api.post<Bookmark>(`/bookmarks/${id}/restore`)
    return response.data
  }, [])

  const archiveBookmark = useCallback(async (id: number): Promise<Bookmark> => {
    const response = await api.post<Bookmark>(`/bookmarks/${id}/archive`)
    return response.data
  }, [])

  const unarchiveBookmark = useCallback(async (id: number): Promise<Bookmark> => {
    const response = await api.post<Bookmark>(`/bookmarks/${id}/unarchive`)
    return response.data
  }, [])

  const fetchMetadata = useCallback(async (url: string): Promise<MetadataPreviewResponse> => {
    const response = await api.get<MetadataPreviewResponse>('/bookmarks/fetch-metadata', {
      params: { url, include_content: true },
    })
    return response.data
  }, [])

  const trackBookmarkUsage = useCallback((id: number): void => {
    // Fire-and-forget: no await, no error handling
    // This is non-critical tracking that shouldn't block user navigation
    api.post(`/bookmarks/${id}/track-usage`).catch(() => {
      // Silently ignore errors
    })
  }, [])

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }))
  }, [])

  return {
    ...state,
    fetchBookmarks,
    fetchBookmark,
    createBookmark,
    updateBookmark,
    deleteBookmark,
    restoreBookmark,
    archiveBookmark,
    unarchiveBookmark,
    fetchMetadata,
    trackBookmarkUsage,
    clearError,
  }
}
