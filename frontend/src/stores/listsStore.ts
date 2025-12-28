/**
 * Zustand store for content lists.
 * Shared state between Settings and Bookmarks pages.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { ContentList, ContentListCreate, ContentListUpdate } from '../types'

interface ListsState {
  lists: ContentList[]
  isLoading: boolean
  error: string | null
}

interface ListsActions {
  fetchLists: () => Promise<void>
  createList: (data: ContentListCreate) => Promise<ContentList>
  updateList: (id: number, data: ContentListUpdate) => Promise<ContentList>
  deleteList: (id: number) => Promise<void>
  clearError: () => void
}

type ListsStore = ListsState & ListsActions

export const useListsStore = create<ListsStore>((set, get) => ({
  // State
  lists: [],
  isLoading: false,
  error: null,

  // Actions
  fetchLists: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.get<ContentList[]>('/lists/')
      set({ lists: response.data, isLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch lists'
      set({ isLoading: false, error: message })
    }
  },

  createList: async (data: ContentListCreate) => {
    const response = await api.post<ContentList>('/lists/', data)
    const newList = response.data
    set({ lists: [...get().lists, newList] })
    return newList
  },

  updateList: async (id: number, data: ContentListUpdate) => {
    const response = await api.patch<ContentList>(`/lists/${id}`, data)
    const updatedList = response.data
    set({
      lists: get().lists.map((list) =>
        list.id === id ? updatedList : list
      ),
    })
    return updatedList
  },

  deleteList: async (id: number) => {
    await api.delete(`/lists/${id}`)
    set({ lists: get().lists.filter((list) => list.id !== id) })
  },

  clearError: () => {
    set({ error: null })
  },
}))
