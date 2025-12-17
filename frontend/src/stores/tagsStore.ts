/**
 * Zustand store for tags.
 * Shared state for tag suggestions and autocomplete.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { Tag, TagCount, TagListResponse, TagRenameRequest } from '../types'

interface TagsState {
  tags: TagCount[]
  isLoading: boolean
  error: string | null
}

interface TagsActions {
  fetchTags: () => Promise<void>
  renameTag: (oldName: string, newName: string) => Promise<Tag>
  deleteTag: (tagName: string) => Promise<void>
  clearError: () => void
}

type TagsStore = TagsState & TagsActions

export const useTagsStore = create<TagsStore>((set, get) => ({
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

  renameTag: async (oldName: string, newName: string) => {
    const body: TagRenameRequest = { new_name: newName }
    const response = await api.patch<Tag>(`/tags/${encodeURIComponent(oldName)}`, body)
    // Update local state - replace old tag name with new name, keeping same count
    const { tags } = get()
    const updatedTags = tags.map((tag) =>
      tag.name === oldName ? { ...tag, name: response.data.name } : tag
    )
    set({ tags: updatedTags })
    return response.data
  },

  deleteTag: async (tagName: string) => {
    await api.delete(`/tags/${encodeURIComponent(tagName)}`)
    // Remove from local state
    const { tags } = get()
    set({ tags: tags.filter((tag) => tag.name !== tagName) })
  },

  clearError: () => {
    set({ error: null })
  },
}))
