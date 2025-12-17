/**
 * Zustand store for user settings.
 * Manages tab order and other user preferences.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { UserSettings, UserSettingsUpdate, TabOrderResponse, TabOrderItem } from '../types'

interface SettingsState {
  settings: UserSettings | null
  computedTabOrder: TabOrderItem[]
  isLoading: boolean
  error: string | null
}

interface SettingsActions {
  fetchSettings: () => Promise<void>
  fetchTabOrder: () => Promise<void>
  updateSettings: (data: UserSettingsUpdate) => Promise<UserSettings>
  clearError: () => void
}

type SettingsStore = SettingsState & SettingsActions

export const useSettingsStore = create<SettingsStore>((set) => ({
  // State
  settings: null,
  computedTabOrder: [],
  isLoading: false,
  error: null,

  // Actions
  fetchSettings: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.get<UserSettings>('/settings/')
      set({ settings: response.data, isLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch settings'
      set({ isLoading: false, error: message })
    }
  },

  fetchTabOrder: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.get<TabOrderResponse>('/settings/tab-order')
      set({ computedTabOrder: response.data.items, isLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tab order'
      set({ isLoading: false, error: message })
    }
  },

  updateSettings: async (data: UserSettingsUpdate) => {
    const response = await api.patch<UserSettings>('/settings/', data)
    set({ settings: response.data })
    return response.data
  },

  clearError: () => {
    set({ error: null })
  },
}))
