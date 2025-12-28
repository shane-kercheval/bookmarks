/**
 * Zustand store for user settings.
 * Manages tab order and other user preferences.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type {
  UserSettings,
  UserSettingsUpdate,
  ComputedTabOrderResponse,
  TabOrderSection,
  TabOrderItem,
  SectionName,
  TabOrder,
} from '../types'

interface SettingsState {
  settings: UserSettings | null
  /** Computed tab order sections from backend */
  computedSections: TabOrderSection[]
  /** Section display order from backend */
  sectionOrder: SectionName[]
  /**
   * Flattened tab order items for backwards compatibility.
   * @deprecated Use computedSections instead for proper section support.
   */
  computedTabOrder: TabOrderItem[]
  isLoading: boolean
  error: string | null
}

interface SettingsActions {
  fetchSettings: () => Promise<void>
  fetchTabOrder: () => Promise<void>
  updateTabOrder: (tabOrder: TabOrder) => Promise<void>
  updateSettings: (data: UserSettingsUpdate) => Promise<UserSettings>
  clearError: () => void
}

type SettingsStore = SettingsState & SettingsActions

/**
 * Flatten all sections' items into a single array for backwards compatibility.
 */
function flattenSections(
  sections: TabOrderSection[],
  sectionOrder: SectionName[]
): TabOrderItem[] {
  return sectionOrder.flatMap((sectionName) => {
    const section = sections.find((s) => s.name === sectionName)
    return section?.items ?? []
  })
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  // State
  settings: null,
  computedSections: [],
  sectionOrder: ['shared', 'bookmarks', 'notes'],
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
      const response = await api.get<ComputedTabOrderResponse>('/settings/tab-order')
      const sections = response.data.sections
      const sectionOrder = response.data.section_order
      set({
        computedSections: sections,
        sectionOrder: sectionOrder,
        // Provide flattened list for backwards compatibility
        computedTabOrder: flattenSections(sections, sectionOrder),
        isLoading: false,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tab order'
      set({ isLoading: false, error: message })
    }
  },

  updateTabOrder: async (tabOrder: TabOrder) => {
    await api.put('/settings/tab-order', tabOrder)
    // Refresh the computed tab order after saving
    const response = await api.get<ComputedTabOrderResponse>('/settings/tab-order')
    const sections = response.data.sections
    const sectionOrder = response.data.section_order
    set({
      computedSections: sections,
      sectionOrder: sectionOrder,
      computedTabOrder: flattenSections(sections, sectionOrder),
    })
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
