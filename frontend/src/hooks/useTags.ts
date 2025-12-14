/**
 * Hook for fetching user's tags for suggestions/autocomplete.
 */
import { useState, useCallback } from 'react'
import { api } from '../services/api'
import type { TagCount, TagListResponse } from '../types'

interface UseTagsState {
  tags: TagCount[]
  isLoading: boolean
  error: string | null
}

interface UseTagsReturn extends UseTagsState {
  fetchTags: () => Promise<void>
  clearError: () => void
}

/**
 * Hook for fetching the user's tags for autocomplete suggestions.
 *
 * Usage:
 * ```tsx
 * const { tags, isLoading, fetchTags } = useTags()
 *
 * useEffect(() => {
 *   fetchTags()
 * }, [])
 * ```
 */
export function useTags(): UseTagsReturn {
  const [state, setState] = useState<UseTagsState>({
    tags: [],
    isLoading: false,
    error: null,
  })

  const fetchTags = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }))

    try {
      const response = await api.get<TagListResponse>('/tags/')
      setState({
        tags: response.data.tags,
        isLoading: false,
        error: null,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tags'
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }))
    }
  }, [])

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }))
  }, [])

  return {
    ...state,
    fetchTags,
    clearError,
  }
}
