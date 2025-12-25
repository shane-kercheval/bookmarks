/**
 * Tests for SettingsBookmarks page.
 *
 * Tests the reset sort orders button functionality.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SettingsBookmarks } from './SettingsBookmarks'
import { useUIPreferencesStore } from '../../stores/uiPreferencesStore'
import { useListsStore } from '../../stores/listsStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useTagsStore } from '../../stores/tagsStore'

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock the stores
vi.mock('../../stores/listsStore', () => ({
  useListsStore: vi.fn(),
}))

vi.mock('../../stores/settingsStore', () => ({
  useSettingsStore: vi.fn(),
}))

vi.mock('../../stores/tagsStore', () => ({
  useTagsStore: vi.fn(),
}))

vi.mock('../../stores/uiPreferencesStore', () => ({
  useUIPreferencesStore: vi.fn(),
}))

describe('SettingsBookmarks', () => {
  const mockFetchLists = vi.fn()
  const mockFetchTabOrder = vi.fn()
  const mockFetchTags = vi.fn()
  const mockClearAllSortOverrides = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    // Setup default store mocks
    vi.mocked(useListsStore).mockReturnValue({
      lists: [],
      isLoading: false,
      fetchLists: mockFetchLists,
      createList: vi.fn(),
      updateList: vi.fn(),
      deleteList: vi.fn(),
    } as ReturnType<typeof useListsStore>)

    vi.mocked(useSettingsStore).mockReturnValue({
      computedTabOrder: [],
      isLoading: false,
      fetchTabOrder: mockFetchTabOrder,
      updateSettings: vi.fn(),
    } as ReturnType<typeof useSettingsStore>)

    vi.mocked(useTagsStore).mockReturnValue({
      tags: [],
      fetchTags: mockFetchTags,
    } as ReturnType<typeof useTagsStore>)

    vi.mocked(useUIPreferencesStore).mockReturnValue({
      sortOverrides: {},
      clearAllSortOverrides: mockClearAllSortOverrides,
    } as unknown as ReturnType<typeof useUIPreferencesStore>)
  })

  describe('reset sort orders button', () => {
    it('should render reset button', () => {
      render(<SettingsBookmarks />)

      expect(screen.getByRole('button', { name: /reset cached sort orders/i })).toBeInTheDocument()
    })

    it('should disable reset button when no sort overrides exist', () => {
      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {},
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })
      expect(resetButton).toBeDisabled()
    })

    it('should enable reset button when sort overrides exist', () => {
      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {
          'all': { sortBy: 'created_at', sortOrder: 'asc' },
        },
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })
      expect(resetButton).not.toBeDisabled()
    })

    it('should show count in tooltip when overrides exist', () => {
      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {
          'all': { sortBy: 'created_at', sortOrder: 'asc' },
          'list:5': { sortBy: 'title', sortOrder: 'desc' },
        },
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })
      expect(resetButton).toHaveAttribute('title', '2 cached sort orders')
    })

    it('should show singular form in tooltip when one override exists', () => {
      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {
          'all': { sortBy: 'created_at', sortOrder: 'asc' },
        },
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })
      expect(resetButton).toHaveAttribute('title', '1 cached sort order')
    })

    it('should show "No cached sort orders" tooltip when no overrides', () => {
      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {},
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })
      expect(resetButton).toHaveAttribute('title', 'No cached sort orders')
    })

    it('should call clearAllSortOverrides when clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {
          'all': { sortBy: 'created_at', sortOrder: 'asc' },
        },
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })
      await user.click(resetButton)

      expect(mockClearAllSortOverrides).toHaveBeenCalledTimes(1)
    })

    it('should not call clearAllSortOverrides when button is disabled and clicked', async () => {
      const user = userEvent.setup()

      vi.mocked(useUIPreferencesStore).mockReturnValue({
        sortOverrides: {},
        clearAllSortOverrides: mockClearAllSortOverrides,
      } as unknown as ReturnType<typeof useUIPreferencesStore>)

      render(<SettingsBookmarks />)

      const resetButton = screen.getByRole('button', { name: /reset cached sort orders/i })

      // Button is disabled, click should not work
      // Using pointer-events: none or similar would prevent the click
      // But in testing, we verify the disabled state
      expect(resetButton).toBeDisabled()

      // Force click attempt (browser would block this)
      await user.click(resetButton).catch(() => {
        // Expected to fail or be ignored
      })

      // Should not have been called
      expect(mockClearAllSortOverrides).not.toHaveBeenCalled()
    })
  })

  describe('page rendering', () => {
    it('should render page title', () => {
      render(<SettingsBookmarks />)

      expect(screen.getByRole('heading', { name: 'Bookmark Settings' })).toBeInTheDocument()
    })

    it('should render Bookmark Lists section', () => {
      render(<SettingsBookmarks />)

      expect(screen.getByRole('heading', { name: 'Bookmark Lists' })).toBeInTheDocument()
    })

    it('should render Sidebar Order section', () => {
      render(<SettingsBookmarks />)

      expect(screen.getByRole('heading', { name: 'Sidebar Order' })).toBeInTheDocument()
    })

    // Note: Data fetching moved to Layout.tsx for centralized loading
  })
})
