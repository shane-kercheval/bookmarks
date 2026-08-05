/**
 * Tests for right sidebar store.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  useRightSidebarStore,
  computeMaxWidth,
  getEffectiveSidebarWidth,
  DEFAULT_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  MIN_CONTENT_WIDTH,
} from './rightSidebarStore'

describe('rightSidebarStore', () => {
  beforeEach(() => {
    useRightSidebarStore.setState({ activePanel: null, width: DEFAULT_SIDEBAR_WIDTH, maximized: false })
    localStorage.clear()
  })

  describe('initial state', () => {
    it('should start with sidebar closed', () => {
      const { activePanel } = useRightSidebarStore.getState()
      expect(activePanel).toBeNull()
    })
  })

  describe('setActivePanel', () => {
    it('should open history panel', () => {
      const { setActivePanel } = useRightSidebarStore.getState()
      setActivePanel('history')
      expect(useRightSidebarStore.getState().activePanel).toBe('history')
    })

    it('should close sidebar when set to null', () => {
      useRightSidebarStore.setState({ activePanel: 'history' })
      const { setActivePanel } = useRightSidebarStore.getState()
      setActivePanel(null)
      expect(useRightSidebarStore.getState().activePanel).toBeNull()
    })

    it('should switch from history to toc', () => {
      useRightSidebarStore.setState({ activePanel: 'history' })
      const { setActivePanel } = useRightSidebarStore.getState()
      setActivePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')
    })

    it('should persist history panel to localStorage', () => {
      const { setActivePanel } = useRightSidebarStore.getState()
      setActivePanel('history')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('history')

      setActivePanel(null)
      expect(localStorage.getItem('right-sidebar-panel')).toBe('')
    })

    it('should not persist toc panel to localStorage', () => {
      const { setActivePanel } = useRightSidebarStore.getState()
      setActivePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('')
    })

    it('should handle localStorage errors gracefully', () => {
      const { setActivePanel } = useRightSidebarStore.getState()
      const originalSetItem = localStorage.setItem
      localStorage.setItem = vi.fn(() => {
        throw new Error('Storage quota exceeded')
      })

      expect(() => setActivePanel('history')).not.toThrow()
      expect(useRightSidebarStore.getState().activePanel).toBe('history')

      localStorage.setItem = originalSetItem
    })
  })

  describe('togglePanel', () => {
    it('should open history when closed', () => {
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('history')
      expect(useRightSidebarStore.getState().activePanel).toBe('history')
    })

    it('should close sidebar when history is already active', () => {
      useRightSidebarStore.setState({ activePanel: 'history' })
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('history')
      expect(useRightSidebarStore.getState().activePanel).toBeNull()
    })

    it('should switch from history to toc', () => {
      useRightSidebarStore.setState({ activePanel: 'history' })
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')
    })

    it('should close sidebar when toc is already active', () => {
      useRightSidebarStore.setState({ activePanel: 'toc' })
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBeNull()
    })

    it('should open toc when closed', () => {
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')
    })

    it('should persist toggled history state to localStorage', () => {
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('history')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('history')

      togglePanel('history')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('')
    })

    it('should not persist toggled toc state to localStorage', () => {
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('')
    })

    it('should persist history when toggling from toc to history', () => {
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('toc')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('')

      togglePanel('history')
      expect(useRightSidebarStore.getState().activePanel).toBe('history')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('history')
    })

    it('should clear persistence when toggling from history to toc', () => {
      const { togglePanel } = useRightSidebarStore.getState()
      togglePanel('history')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('history')

      togglePanel('toc')
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')
      expect(localStorage.getItem('right-sidebar-panel')).toBe('')
    })
  })

  describe('setWidth', () => {
    it('should update width within valid range', () => {
      const { setWidth } = useRightSidebarStore.getState()
      setWidth(500)
      expect(useRightSidebarStore.getState().width).toBe(500)
    })

    it('should clamp width to minimum boundary', () => {
      const { setWidth } = useRightSidebarStore.getState()
      setWidth(100)
      expect(useRightSidebarStore.getState().width).toBe(MIN_SIDEBAR_WIDTH)
    })

    it('should accept large widths (dynamic max handled at resize time)', () => {
      const { setWidth } = useRightSidebarStore.getState()
      setWidth(1000)
      expect(useRightSidebarStore.getState().width).toBe(1000)
    })

    it('should persist width to localStorage', () => {
      const { setWidth } = useRightSidebarStore.getState()
      setWidth(600)
      expect(localStorage.getItem('right-sidebar-width')).toBe('600')
    })

    it('should handle localStorage errors gracefully', () => {
      const { setWidth } = useRightSidebarStore.getState()
      const originalSetItem = localStorage.setItem
      localStorage.setItem = vi.fn(() => {
        throw new Error('Storage quota exceeded')
      })

      expect(() => setWidth(500)).not.toThrow()
      expect(useRightSidebarStore.getState().width).toBe(500)

      localStorage.setItem = originalSetItem
    })
  })

  describe('getEffectiveSidebarWidth', () => {
    it('clamps the stored width to the max', () => {
      expect(getEffectiveSidebarWidth(400, false, 840)).toBe(400)
      expect(getEffectiveSidebarWidth(900, false, 840)).toBe(840)
    })

    it('follows the live max when maximized, regardless of stored width', () => {
      expect(getEffectiveSidebarWidth(400, true, 840)).toBe(840)
    })
  })

  describe('computeMaxWidth', () => {
    it('subtracts left sidebar and reserved content width from the viewport', () => {
      // 1440 - 288 (expanded left) - 600 reserved = 552
      expect(computeMaxWidth(1440, 288)).toBe(1440 - 288 - MIN_CONTENT_WIDTH)
    })

    it('grows when the left sidebar is collapsed', () => {
      // Same viewport, collapsed left sidebar (48) leaves more room.
      expect(computeMaxWidth(1440, 48)).toBeGreaterThan(computeMaxWidth(1440, 288))
    })

    it('floors at MIN_SIDEBAR_WIDTH on narrow viewports', () => {
      // 900 - 288 - 600 = 12, below the floor.
      expect(computeMaxWidth(900, 288)).toBe(MIN_SIDEBAR_WIDTH)
    })
  })

  describe('maximize', () => {
    it('toggleMaximized flips and persists the flag', () => {
      const { toggleMaximized } = useRightSidebarStore.getState()
      toggleMaximized()
      expect(useRightSidebarStore.getState().maximized).toBe(true)
      expect(localStorage.getItem('right-sidebar-maximized')).toBe('true')

      toggleMaximized()
      expect(useRightSidebarStore.getState().maximized).toBe(false)
      expect(localStorage.getItem('right-sidebar-maximized')).toBe('false')
    })

    it('setMaximized does not touch the stored width (restore target preserved)', () => {
      const { setWidth, setMaximized } = useRightSidebarStore.getState()
      setWidth(700)
      setMaximized(true)
      expect(useRightSidebarStore.getState().width).toBe(700)
      setMaximized(false)
      expect(useRightSidebarStore.getState().width).toBe(700)
    })

    it('handles localStorage errors gracefully', () => {
      const { setMaximized } = useRightSidebarStore.getState()
      const originalSetItem = localStorage.setItem
      localStorage.setItem = vi.fn(() => {
        throw new Error('Storage quota exceeded')
      })

      expect(() => setMaximized(true)).not.toThrow()
      expect(useRightSidebarStore.getState().maximized).toBe(true)

      localStorage.setItem = originalSetItem
    })
  })

  describe('initialization from localStorage', () => {
    it('should initialize maximized from localStorage when set to true', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-maximized', 'true')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().maximized).toBe(true)
    })

    it('should default maximized to false when localStorage is empty', async () => {
      vi.resetModules()
      localStorage.clear()

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().maximized).toBe(false)
    })

    it('should use default width when localStorage is empty', async () => {
      vi.resetModules()
      localStorage.clear()

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().width).toBe(DEFAULT_SIDEBAR_WIDTH)
    })

    it('should initialize width from localStorage when present', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-width', '650')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().width).toBe(650)
    })

    it('should fall back to default width when localStorage has invalid value', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-width', 'not-a-number')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().width).toBe(DEFAULT_SIDEBAR_WIDTH)
    })

    it('should fall back to default width when localStorage value is below minimum', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-width', '100')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().width).toBe(DEFAULT_SIDEBAR_WIDTH)
    })

    it('should start closed when localStorage is empty', async () => {
      vi.resetModules()
      localStorage.clear()

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().activePanel).toBeNull()
    })

    it('should initialize panel from localStorage when valid', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-panel', 'history')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().activePanel).toBe('history')
    })

    it('should not restore toc panel from localStorage', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-panel', 'toc')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().activePanel).toBeNull()
    })

    it('should initialize closed when localStorage has invalid value', async () => {
      vi.resetModules()
      localStorage.clear()
      localStorage.setItem('right-sidebar-panel', 'invalid')

      const { useRightSidebarStore: freshStore } = await import('./rightSidebarStore')
      expect(freshStore.getState().activePanel).toBeNull()
    })
  })
})
