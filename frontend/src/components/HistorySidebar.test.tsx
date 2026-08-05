/**
 * Tests for HistorySidebar component.
 *
 * Focuses on audit event handling:
 * - Action dots rendered for all entries
 * - Audit actions (null version) don't show version badge
 * - Audit actions don't show restore button
 * - Content actions show version badge and diff view
 * - RESTORE actions show diff and restore button
 * - latestVersion computed from first non-null version
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HistorySidebar } from './HistorySidebar'
import type { HistoryEntry } from '../types'

// Mock the history hooks
const mockUseEntityHistory = vi.fn()
const mockUseVersionDiff = vi.fn()
const mockUseRestoreToVersion = vi.fn()
vi.mock('../hooks/useHistory', () => ({
  useEntityHistory: (...args: unknown[]) => mockUseEntityHistory(...args),
  useVersionDiff: (...args: unknown[]) => mockUseVersionDiff(...args),
  useRestoreToVersion: () => mockUseRestoreToVersion(),
}))

// Mock the sidebar store
vi.mock('../stores/rightSidebarStore', () => ({
  useRightSidebarStore: (
    selector: (state: { width: number; maximized: boolean; toggleMaximized: () => void; setMaximized: () => void }) => unknown,
  ) => selector({ width: 500, maximized: false, toggleMaximized: () => {}, setMaximized: () => {} }),
  MIN_SIDEBAR_WIDTH: 300,
  MIN_CONTENT_WIDTH: 400,
  computeMaxWidth: (innerWidth: number, leftSidebarWidth: number) =>
    Math.max(300, innerWidth - leftSidebarWidth - 400),
  getEffectiveSidebarWidth: (storeWidth: number, maximized: boolean, maxWidth: number) =>
    maximized ? maxWidth : Math.min(storeWidth, maxWidth),
}))

function createEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    id: 'entry-1',
    content_type: 'bookmark',
    content_id: 'entity-1',
    action: 'update',
    version: 2,
    metadata_snapshot: { title: 'Test' },
    changed_fields: null,
    source: 'web',
    auth_type: 'auth0',
    token_prefix: null,
    created_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

function renderSidebar(props: { isDeleted?: boolean } = {}): void {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <HistorySidebar
        entityType="bookmark"
        entityId="entity-1"
        onClose={vi.fn()}
        onRestored={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('HistorySidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseVersionDiff.mockReturnValue({ data: null })
    mockUseRestoreToVersion.mockReturnValue({ mutate: vi.fn(), isPending: false })
  })

  describe('action dots', () => {
    it('test__action_dots__rendered_for_all_entries', () => {
      const entries = [
        createEntry({ id: '1', action: 'create', version: 1 }),
        createEntry({ id: '2', action: 'update', version: 2 }),
        createEntry({ id: '3', action: 'restore', version: 3 }),
        createEntry({ id: '4', action: 'delete', version: null }),
        createEntry({ id: '5', action: 'undelete', version: null }),
        createEntry({ id: '6', action: 'archive', version: null }),
        createEntry({ id: '7', action: 'unarchive', version: null }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Each entry should have an action dot
      const dots = screen.getAllByTestId('action-dot')
      expect(dots).toHaveLength(7)
    })
  })

  describe('audit action display', () => {
    it('test__audit_actions__do_not_show_version_badge', () => {
      const entries = [
        createEntry({ id: '1', action: 'update', version: 2 }),
        createEntry({ id: '2', action: 'delete', version: null }),
        createEntry({ id: '3', action: 'undelete', version: null }),
        createEntry({ id: '4', action: 'archive', version: null }),
        createEntry({ id: '5', action: 'unarchive', version: null }),
        createEntry({ id: '6', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Latest content version shows "Current", older shows version badge
      expect(screen.getByText('Current')).toBeInTheDocument()
      expect(screen.getByText('v1')).toBeInTheDocument()

      // Audit actions should NOT show version badges (no v for null versions)
      // Only v1 should have a version badge (v2 shows as "Current")
      const versionBadges = screen.getAllByText(/^v\d+$/)
      expect(versionBadges).toHaveLength(1)
    })

    it('test__audit_actions__do_not_show_restore_button', () => {
      const entries = [
        createEntry({ id: '1', action: 'update', version: 3 }),
        createEntry({ id: '2', action: 'delete', version: null }),
        createEntry({ id: '3', action: 'update', version: 2 }),
        createEntry({ id: '4', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Restore buttons should only appear for non-latest content versions (v2 and v1)
      const restoreButtons = screen.getAllByText('Restore')
      expect(restoreButtons).toHaveLength(2)
    })

    it('test__content_actions__show_version_badge', () => {
      const entries = [
        createEntry({ id: '1', action: 'restore', version: 3 }),
        createEntry({ id: '2', action: 'update', version: 2 }),
        createEntry({ id: '3', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      expect(screen.getByText('Current')).toBeInTheDocument()
      expect(screen.getByText('v2')).toBeInTheDocument()
      expect(screen.getByText('v1')).toBeInTheDocument()
    })

    it('test__restore_action__shows_restore_button_like_update', () => {
      const entries = [
        createEntry({ id: '1', action: 'update', version: 4 }),
        createEntry({ id: '2', action: 'restore', version: 3 }),
        createEntry({ id: '3', action: 'update', version: 2 }),
        createEntry({ id: '4', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // v3 (restore), v2 (update), v1 (create) should all have restore buttons
      const restoreButtons = screen.getAllByText('Restore')
      expect(restoreButtons).toHaveLength(3)
    })
  })

  describe('latestVersion computation', () => {
    it('test__latest_version__ignores_audit_entries_with_null_version', () => {
      // Audit entries at the top (most recent) should be skipped
      const entries = [
        createEntry({ id: '1', action: 'archive', version: null }),
        createEntry({ id: '2', action: 'delete', version: null }),
        createEntry({ id: '3', action: 'update', version: 3 }),
        createEntry({ id: '4', action: 'update', version: 2 }),
        createEntry({ id: '5', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // latestVersion should be 3 (first non-null), so v2 and v1 get restore buttons
      const restoreButtons = screen.getAllByText('Restore')
      expect(restoreButtons).toHaveLength(2) // v2 and v1
    })

    it('test__latest_version__first_content_entry_has_no_restore_button', () => {
      const entries = [
        createEntry({ id: '1', action: 'undelete', version: null }),
        createEntry({ id: '2', action: 'update', version: 3 }),
        createEntry({ id: '3', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // v3 is the latest content version - no restore button
      // v1 gets a restore button
      const restoreButtons = screen.getAllByText('Restore')
      expect(restoreButtons).toHaveLength(1)
    })
  })

  describe('diff view interaction', () => {
    it('test__clicking_content_entry__opens_diff_view', () => {
      mockUseVersionDiff.mockReturnValue({
        data: {
          before_content: 'old content',
          after_content: 'test content',
          before_metadata: { title: 'Test' },
          after_metadata: { title: 'Test' },
          warnings: null,
        },
      })

      const entries = [
        createEntry({ id: '1', action: 'update', version: 2 }),
        createEntry({ id: '2', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Click on Current (v2) entry
      fireEvent.click(screen.getByText('Current'))

      // The entry should be highlighted (bg-blue-50 class)
      const currentElement = screen.getByText('Current').closest('[class*="bg-blue-50"]')
      expect(currentElement).toBeInTheDocument()
    })

    it('test__metadata_only_payload__shows_metadata_changes_without_content_diff', () => {
      mockUseVersionDiff.mockReturnValue({
        data: {
          before_content: null,
          after_content: null,
          before_metadata: { title: 'Old Title', tags: ['a'] },
          after_metadata: { title: 'New Title', tags: ['a'] },
          warnings: null,
        },
      })

      const entries = [
        createEntry({ id: '1', action: 'update', version: 2 }),
        createEntry({ id: '2', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()
      fireEvent.click(screen.getByText('Current'))

      // Metadata changes rendered
      expect(screen.getByText('Title:')).toBeInTheDocument()
      expect(screen.getByText('Old Title')).toBeInTheDocument()
      expect(screen.getByText('New Title')).toBeInTheDocument()

      // No content diff rendered (both content fields null)
      expect(screen.queryByTestId('diff-viewer')).not.toBeInTheDocument()
    })

    it('test__content_and_metadata_payload__shows_both_sections', () => {
      mockUseVersionDiff.mockReturnValue({
        data: {
          before_content: 'old content',
          after_content: 'new content',
          before_metadata: { title: 'Old Title', tags: [] },
          after_metadata: { title: 'New Title', tags: [] },
          warnings: null,
        },
      })

      const entries = [
        createEntry({ id: '1', action: 'update', version: 2 }),
        createEntry({ id: '2', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()
      fireEvent.click(screen.getByText('Current'))

      // Metadata changes rendered
      expect(screen.getByText('Title:')).toBeInTheDocument()

      // Content diff rendered
      expect(screen.getByTestId('diff-viewer')).toBeInTheDocument()
    })

    it('test__warnings_present__shows_warning_banner', () => {
      mockUseVersionDiff.mockReturnValue({
        data: {
          before_content: null,
          after_content: 'some content',
          before_metadata: { title: 'Test', tags: [] },
          after_metadata: { title: 'Test', tags: [] },
          warnings: ['Some changes could not be reconstructed'],
        },
      })

      const entries = [
        createEntry({ id: '1', action: 'update', version: 2 }),
        createEntry({ id: '2', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()
      fireEvent.click(screen.getByText('Current'))

      expect(screen.getByText('Warning: Some changes could not be fully reconstructed')).toBeInTheDocument()
    })

    it('test__clicking_audit_entry__closes_open_diff_view', () => {
      mockUseVersionDiff.mockReturnValue({
        data: {
          before_content: 'old content',
          after_content: 'test content',
          before_metadata: { title: 'Test' },
          after_metadata: { title: 'Test' },
          warnings: null,
        },
      })

      const entries = [
        createEntry({ id: '1', action: 'update', version: 3 }),
        createEntry({ id: '2', action: 'delete', version: null }),
        createEntry({ id: '3', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Click on Current (v3) to open diff
      fireEvent.click(screen.getByText('Current'))
      expect(screen.getByText('Current').closest('[class*="bg-blue-50"]')).toBeInTheDocument()

      // Click on the audit entry (bg-gray-50/50 row without version badge)
      // The audit entry has the 'bg-gray-50/50' class (audit styling)
      const dots = screen.getAllByTestId('action-dot')
      // dots[0] = update (v3), dots[1] = delete (audit), dots[2] = create (v1)
      const auditDot = dots[1]
      const auditRow = auditDot.closest('[class*="bg-gray-50"]')!
      fireEvent.click(auditRow)
      expect(screen.getByText('Current').closest('[class*="bg-blue-50"]')).toBeNull()
    })
  })

  describe('change indicators', () => {
    it('test__change_indicators__shown_when_changed_fields_present', () => {
      const entries = [
        createEntry({ id: '1', action: 'update', version: 2, changed_fields: ['content', 'title'] }),
        createEntry({ id: '2', action: 'create', version: 1, changed_fields: ['content', 'title', 'url'] }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Both entries have changed_fields, so indicators should render
      const indicators = screen.getAllByTestId('change-indicators')
      expect(indicators).toHaveLength(2)
    })

    it('test__change_indicators__not_shown_for_null_changed_fields', () => {
      const entries = [
        createEntry({ id: '1', action: 'delete', version: null, changed_fields: null }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      expect(screen.queryByTestId('change-indicators')).not.toBeInTheDocument()
    })
  })

  describe('deleted entity', () => {
    it('test__is_deleted__hides_all_restore_buttons', () => {
      const entries = [
        createEntry({ id: '1', action: 'delete', version: null }),
        createEntry({ id: '2', action: 'update', version: 3 }),
        createEntry({ id: '3', action: 'update', version: 2 }),
        createEntry({ id: '4', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar({ isDeleted: true })

      expect(screen.queryByText('Restore')).not.toBeInTheDocument()
    })
  })

  describe('pagination', () => {
    it('test__pagination__hidden_when_total_within_single_page', () => {
      const entries = [
        createEntry({ id: '1', action: 'update', version: 2 }),
        createEntry({ id: '2', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: 2, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      expect(screen.queryByText('Previous')).not.toBeInTheDocument()
      expect(screen.queryByText('Next')).not.toBeInTheDocument()
      expect(screen.queryByText(/Showing/)).not.toBeInTheDocument()
    })

    it('test__pagination__shown_with_correct_text_and_button_states', () => {
      const entries = Array.from({ length: 50 }, (_, i) =>
        createEntry({ id: `entry-${i}`, action: 'update', version: 75 - i })
      )

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: 75, offset: 0, limit: 50, has_more: true },
        isLoading: false,
      })

      renderSidebar()

      expect(screen.getByText('Showing 1-50 of 75')).toBeInTheDocument()
      expect(screen.getByLabelText('Previous page')).toBeDisabled()
      expect(screen.getByLabelText('Next page')).toBeEnabled()
    })

    it('test__pagination__next_passes_correct_offset_to_hook', () => {
      const entries = Array.from({ length: 50 }, (_, i) =>
        createEntry({ id: `entry-${i}`, action: 'update', version: 75 - i })
      )

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: 75, offset: 0, limit: 50, has_more: true },
        isLoading: false,
      })

      renderSidebar()

      // Navigate to page 2
      fireEvent.click(screen.getByLabelText('Next page'))

      // Find the call with offset: 50
      const calls = mockUseEntityHistory.mock.calls
      const lastCall = calls[calls.length - 1]
      expect(lastCall[2]).toEqual({ limit: 50, offset: 50 })
    })

    it('test__pagination__page_beyond_first_shows_no_current_label', () => {
      // Page 0: latest entries with has_more=true
      const page0Entries = Array.from({ length: 50 }, (_, i) =>
        createEntry({ id: `p0-${i}`, action: 'update', version: 75 - i })
      )
      mockUseEntityHistory.mockReturnValue({
        data: { items: page0Entries, total: 75, offset: 0, limit: 50, has_more: true },
        isLoading: false,
      })

      renderSidebar()
      expect(screen.getByText('Current')).toBeInTheDocument()

      // Page 1: older entries
      const page1Entries = [
        createEntry({ id: 'p1-0', action: 'update', version: 25 }),
        createEntry({ id: 'p1-1', action: 'update', version: 24 }),
        createEntry({ id: 'p1-2', action: 'create', version: 1 }),
      ]
      mockUseEntityHistory.mockReturnValue({
        data: { items: page1Entries, total: 75, offset: 50, limit: 50, has_more: false },
        isLoading: false,
      })

      fireEvent.click(screen.getByLabelText('Next page'))

      // No entry should be labeled "Current" on page > 0
      expect(screen.queryByText('Current')).not.toBeInTheDocument()
      // All versions should show their version badge
      expect(screen.getByText('v25')).toBeInTheDocument()
      expect(screen.getByText('v24')).toBeInTheDocument()
      expect(screen.getByText('v1')).toBeInTheDocument()
    })

    it('test__pagination__page_beyond_first_shows_restore_on_all_content_entries', () => {
      // Page 0: latest entries with has_more=true
      const page0Entries = Array.from({ length: 50 }, (_, i) =>
        createEntry({ id: `p0-${i}`, action: 'update', version: 75 - i })
      )
      mockUseEntityHistory.mockReturnValue({
        data: { items: page0Entries, total: 75, offset: 0, limit: 50, has_more: true },
        isLoading: false,
      })

      renderSidebar()

      // Page 1: older entries including an audit action
      const page1Entries = [
        createEntry({ id: 'p1-0', action: 'update', version: 25 }),
        createEntry({ id: 'p1-1', action: 'delete', version: null }),
        createEntry({ id: 'p1-2', action: 'update', version: 23 }),
        createEntry({ id: 'p1-3', action: 'create', version: 1 }),
      ]
      mockUseEntityHistory.mockReturnValue({
        data: { items: page1Entries, total: 75, offset: 50, limit: 50, has_more: false },
        isLoading: false,
      })

      fireEvent.click(screen.getByLabelText('Next page'))

      // All non-audit content versions should have restore buttons (v25, v23, v1)
      const restoreButtons = screen.getAllByText('Restore')
      expect(restoreButtons).toHaveLength(3)
    })
  })

  describe('audit entries with versions', () => {
    it('test__audit_actions_with_version__do_not_show_restore_button', () => {
      // Legacy data where archive/unarchive entries have version numbers
      const entries = [
        createEntry({ id: '1', action: 'unarchive', version: 4 }),
        createEntry({ id: '2', action: 'archive', version: 3 }),
        createEntry({ id: '3', action: 'update', version: 2 }),
        createEntry({ id: '4', action: 'create', version: 1 }),
      ]

      mockUseEntityHistory.mockReturnValue({
        data: { items: entries, total: entries.length, offset: 0, limit: 50, has_more: false },
        isLoading: false,
      })

      renderSidebar()

      // Only v2 and v1 should have restore buttons (not archive/unarchive even with versions)
      const restoreButtons = screen.getAllByText('Restore')
      expect(restoreButtons).toHaveLength(2)
    })
  })
})
