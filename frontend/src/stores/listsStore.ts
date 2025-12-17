/**
 * Zustand store for bookmark lists.
 * Shared state between Settings and Bookmarks pages.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { BookmarkList, BookmarkListCreate, BookmarkListUpdate } from '../types'

interface ListsState {
  lists: BookmarkList[]
  isLoading: boolean
  error: string | null
}

interface ListsActions {
  fetchLists: () => Promise<void>
  createList: (data: BookmarkListCreate) => Promise<BookmarkList>
  updateList: (id: number, data: BookmarkListUpdate) => Promise<BookmarkList>
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
      const response = await api.get<BookmarkList[]>('/lists/')
      set({ lists: response.data, isLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch lists'
      set({ isLoading: false, error: message })
    }
  },

  createList: async (data: BookmarkListCreate) => {
    const response = await api.post<BookmarkList>('/lists/', data)
    const newList = response.data
    set({ lists: [...get().lists, newList] })
    return newList
  },

  updateList: async (id: number, data: BookmarkListUpdate) => {
    const response = await api.patch<BookmarkList>(`/lists/${id}`, data)
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
