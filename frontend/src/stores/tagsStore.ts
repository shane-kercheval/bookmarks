/**
 * Zustand store for tags.
 * Shared state for tag suggestions and autocomplete.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { TagCount, TagListResponse } from '../types'

interface TagsState {
  tags: TagCount[]
  isLoading: boolean
  error: string | null
}

interface TagsActions {
  fetchTags: () => Promise<void>
  clearError: () => void
}

type TagsStore = TagsState & TagsActions

export const useTagsStore = create<TagsStore>((set) => ({
  // State
  tags: [],
  isLoading: false,
  error: null,

  // Actions
  fetchTags: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.get<TagListResponse>('/tags/')
      set({ tags: response.data.tags, isLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tags'
      set({ isLoading: false, error: message })
    }
  },

  clearError: () => {
    set({ error: null })
  },
}))
