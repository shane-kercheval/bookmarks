/**
 * Hook for managing bookmarks - fetching, creating, updating, deleting.
 */
import { useState, useCallback } from 'react'
import { api } from '../services/api'
import type {
  Bookmark,
  BookmarkCreate,
  BookmarkUpdate,
  BookmarkListResponse,
  BookmarkSearchParams,
  MetadataPreviewResponse,
} from '../types'

interface UseBookmarksState {
  bookmarks: Bookmark[]
  total: number
  isLoading: boolean
  error: string | null
}

interface UseBookmarksReturn extends UseBookmarksState {
  fetchBookmarks: (params?: BookmarkSearchParams) => Promise<void>
  createBookmark: (data: BookmarkCreate) => Promise<Bookmark>
  updateBookmark: (id: number, data: BookmarkUpdate) => Promise<Bookmark>
  deleteBookmark: (id: number) => Promise<void>
  fetchMetadata: (url: string) => Promise<MetadataPreviewResponse>
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
  })

  const fetchBookmarks = useCallback(async (params: BookmarkSearchParams = {}) => {
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

      const queryString = queryParams.toString()
      const url = queryString ? `/bookmarks/?${queryString}` : '/bookmarks/'

      const response = await api.get<BookmarkListResponse>(url)

      setState({
        bookmarks: response.data.items,
        total: response.data.total,
        isLoading: false,
        error: null,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch bookmarks'
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }))
    }
  }, [])

  const createBookmark = useCallback(async (data: BookmarkCreate): Promise<Bookmark> => {
    console.log('Creating bookmark with data:', JSON.stringify(data, null, 2))
    const response = await api.post<Bookmark>('/bookmarks/', data)
    console.log('Bookmark created:', response.data)
    return response.data
  }, [])

  const updateBookmark = useCallback(
    async (id: number, data: BookmarkUpdate): Promise<Bookmark> => {
      const response = await api.patch<Bookmark>(`/bookmarks/${id}`, data)
      return response.data
    },
    []
  )

  const deleteBookmark = useCallback(async (id: number): Promise<void> => {
    await api.delete(`/bookmarks/${id}`)
  }, [])

  const fetchMetadata = useCallback(async (url: string): Promise<MetadataPreviewResponse> => {
    const response = await api.get<MetadataPreviewResponse>('/bookmarks/fetch-metadata', {
      params: { url },
    })
    return response.data
  }, [])

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }))
  }, [])

  return {
    ...state,
    fetchBookmarks,
    createBookmark,
    updateBookmark,
    deleteBookmark,
    fetchMetadata,
    clearError,
  }
}
