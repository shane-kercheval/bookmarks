/**
 * Tests for useUIPreferencesStore.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useUIPreferencesStore } from './uiPreferencesStore'

describe('useUIPreferencesStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useUIPreferencesStore.setState({
      fullWidthLayout: false,
      bookmarkSortBy: 'last_used_at',
      bookmarkSortOrder: 'desc',
      sortOverrides: {},
    })
  })

  describe('initial state', () => {
    it('has fullWidthLayout as false by default', () => {
      const { fullWidthLayout } = useUIPreferencesStore.getState()
      expect(fullWidthLayout).toBe(false)
    })
  })

  describe('toggleFullWidthLayout', () => {
    it('toggles from false to true', () => {
      const { toggleFullWidthLayout } = useUIPreferencesStore.getState()
      toggleFullWidthLayout()

      const { fullWidthLayout } = useUIPreferencesStore.getState()
      expect(fullWidthLayout).toBe(true)
    })

    it('toggles from true to false', () => {
      useUIPreferencesStore.setState({ fullWidthLayout: true })
      const { toggleFullWidthLayout } = useUIPreferencesStore.getState()
      toggleFullWidthLayout()

      const { fullWidthLayout } = useUIPreferencesStore.getState()
      expect(fullWidthLayout).toBe(false)
    })

    it('toggles multiple times', () => {
      const { toggleFullWidthLayout } = useUIPreferencesStore.getState()

      toggleFullWidthLayout()
      expect(useUIPreferencesStore.getState().fullWidthLayout).toBe(true)

      toggleFullWidthLayout()
      expect(useUIPreferencesStore.getState().fullWidthLayout).toBe(false)

      toggleFullWidthLayout()
      expect(useUIPreferencesStore.getState().fullWidthLayout).toBe(true)
    })
  })

  describe('setFullWidthLayout', () => {
    it('sets to true', () => {
      const { setFullWidthLayout } = useUIPreferencesStore.getState()
      setFullWidthLayout(true)

      const { fullWidthLayout } = useUIPreferencesStore.getState()
      expect(fullWidthLayout).toBe(true)
    })

    it('sets to false', () => {
      useUIPreferencesStore.setState({ fullWidthLayout: true })
      const { setFullWidthLayout } = useUIPreferencesStore.getState()
      setFullWidthLayout(false)

      const { fullWidthLayout } = useUIPreferencesStore.getState()
      expect(fullWidthLayout).toBe(false)
    })
  })

  describe('sortOverrides', () => {
    describe('initial state', () => {
      it('has empty sortOverrides by default', () => {
        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides).toEqual({})
      })

      it('has default bookmarkSortBy as last_used_at', () => {
        const { bookmarkSortBy } = useUIPreferencesStore.getState()
        expect(bookmarkSortBy).toBe('last_used_at')
      })

      it('has default bookmarkSortOrder as desc', () => {
        const { bookmarkSortOrder } = useUIPreferencesStore.getState()
        expect(bookmarkSortOrder).toBe('desc')
      })
    })

    describe('setSortOverride', () => {
      it('sets override for a specific view key', () => {
        const { setSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides['all']).toEqual({
          sortBy: 'created_at',
          sortOrder: 'asc',
        })
      })

      it('sets override for list view key', () => {
        const { setSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('list:5', 'title', 'asc')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides['list:5']).toEqual({
          sortBy: 'title',
          sortOrder: 'asc',
        })
      })

      it('sets multiple overrides for different views', () => {
        const { setSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'desc')
        setSortOverride('archived', 'archived_at', 'desc')
        setSortOverride('trash', 'deleted_at', 'desc')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(Object.keys(sortOverrides)).toHaveLength(3)
        expect(sortOverrides['all']).toEqual({ sortBy: 'created_at', sortOrder: 'desc' })
        expect(sortOverrides['archived']).toEqual({ sortBy: 'archived_at', sortOrder: 'desc' })
        expect(sortOverrides['trash']).toEqual({ sortBy: 'deleted_at', sortOrder: 'desc' })
      })

      it('overwrites existing override for same view key', () => {
        const { setSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')
        setSortOverride('all', 'updated_at', 'desc')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides['all']).toEqual({
          sortBy: 'updated_at',
          sortOrder: 'desc',
        })
      })
    })

    describe('clearSortOverride', () => {
      it('clears override for a specific view key', () => {
        const { setSortOverride, clearSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')
        clearSortOverride('all')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides['all']).toBeUndefined()
      })

      it('does not affect other view keys when clearing one', () => {
        const { setSortOverride, clearSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')
        setSortOverride('list:5', 'title', 'asc')
        clearSortOverride('all')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides['all']).toBeUndefined()
        expect(sortOverrides['list:5']).toEqual({ sortBy: 'title', sortOrder: 'asc' })
      })

      it('handles clearing non-existent key gracefully', () => {
        const { clearSortOverride } = useUIPreferencesStore.getState()
        clearSortOverride('nonexistent')

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides).toEqual({})
      })
    })

    describe('clearAllSortOverrides', () => {
      it('clears all sort overrides', () => {
        const { setSortOverride, clearAllSortOverrides } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')
        setSortOverride('archived', 'archived_at', 'desc')
        setSortOverride('list:5', 'title', 'asc')

        clearAllSortOverrides()

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides).toEqual({})
      })

      it('handles clearing when already empty', () => {
        const { clearAllSortOverrides } = useUIPreferencesStore.getState()
        clearAllSortOverrides()

        const { sortOverrides } = useUIPreferencesStore.getState()
        expect(sortOverrides).toEqual({})
      })
    })

    describe('getSortOverride', () => {
      it('returns override for existing view key', () => {
        const { setSortOverride, getSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')

        const override = getSortOverride('all')
        expect(override).toEqual({ sortBy: 'created_at', sortOrder: 'asc' })
      })

      it('returns undefined for non-existent view key', () => {
        const { getSortOverride } = useUIPreferencesStore.getState()
        const override = getSortOverride('nonexistent')
        expect(override).toBeUndefined()
      })

      it('returns correct override after updates', () => {
        const { setSortOverride, getSortOverride } = useUIPreferencesStore.getState()
        setSortOverride('all', 'created_at', 'asc')
        setSortOverride('all', 'title', 'desc')

        const override = getSortOverride('all')
        expect(override).toEqual({ sortBy: 'title', sortOrder: 'desc' })
      })
    })
  })
})
