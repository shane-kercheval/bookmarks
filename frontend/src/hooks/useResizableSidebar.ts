/**
 * Shared drag-to-resize logic for right sidebar panels.
 * Handles width constraints, drag state, responsive breakpoint, maximize mode,
 * and recompute on viewport / left-sidebar width changes.
 */
import { useReducer, useState, useEffect, useCallback } from 'react'
import { useRightSidebarStore, computeMaxWidth, getEffectiveSidebarWidth } from '../stores/rightSidebarStore'
import { DESKTOP_SIDEBAR_ID } from '../constants/sidebar'

const MD_BREAKPOINT = 768

/**
 * Measure the current maximum sidebar width from the live DOM/window. The left
 * sidebar's width is read from the desktop sidebar element (it collapses
 * w-12 ↔ w-72). Thin wrapper over the pure computeMaxWidth so the arithmetic
 * stays testable.
 */
export function measureMaxSidebarWidth(): number {
  const leftSidebar = document.getElementById(DESKTOP_SIDEBAR_ID)
  const leftSidebarWidth = leftSidebar?.getBoundingClientRect().width ?? 0
  return computeMaxWidth(window.innerWidth, leftSidebarWidth)
}

interface EffectiveSidebarMetrics {
  /** The sidebar's effective rendered width (clamped/maximized on desktop). */
  effectiveWidth: number
  isDesktop: boolean
}

/**
 * Read-only, reactive view of the right sidebar's effective geometry: the
 * width it actually renders at and whether we're above the desktop
 * breakpoint. For consumers that lay content out around the sidebar (the app
 * layout margin, the public shared-item layout) without needing drag state —
 * useResizableSidebar composes this and adds the drag interaction.
 */
export function useEffectiveSidebarMetrics(): EffectiveSidebarMetrics {
  const storeWidth = useRightSidebarStore((state) => state.width)
  const maximized = useRightSidebarStore((state) => state.maximized)
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= MD_BREAKPOINT : true
  )
  // Forces a width recompute when the viewport or left-sidebar width changes.
  // Kept separate from the persisted `width` so a transient viewport shrink
  // clamps the rendered width without overwriting the user's chosen width.
  const [, recompute] = useReducer((n: number) => n + 1, 0)

  useEffect(() => {
    const onResize = (): void => {
      setIsDesktop(window.innerWidth >= MD_BREAKPOINT)
      recompute()
    }
    window.addEventListener('resize', onResize)

    // Track the left sidebar's animated collapse/expand so the clamped (and,
    // when maximized, the effective) width stay in step with it.
    const leftSidebar = document.getElementById(DESKTOP_SIDEBAR_ID)
    let observer: ResizeObserver | undefined
    if (leftSidebar && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => recompute())
      observer.observe(leftSidebar)
    }

    return () => {
      window.removeEventListener('resize', onResize)
      observer?.disconnect()
    }
  }, [])

  const effectiveWidth = isDesktop
    ? getEffectiveSidebarWidth(storeWidth, maximized, measureMaxSidebarWidth())
    : storeWidth

  return { effectiveWidth, isDesktop }
}

interface ResizableSidebarResult {
  width: number
  isDesktop: boolean
  isDragging: boolean
  handleMouseDown: (e: React.MouseEvent) => void
}

export function useResizableSidebar(): ResizableSidebarResult {
  const setWidth = useRightSidebarStore((state) => state.setWidth)
  const maximized = useRightSidebarStore((state) => state.maximized)
  const setMaximized = useRightSidebarStore((state) => state.setMaximized)
  const [isDragging, setIsDragging] = useState(false)
  const { effectiveWidth: width, isDesktop } = useEffectiveSidebarMetrics()

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent): void => {
      const newWidth = window.innerWidth - e.clientX
      setWidth(Math.min(newWidth, measureMaxSidebarWidth()))
      // A manual drag is an explicit width choice — leave maximize mode. Guarded
      // so it fires once; the effect re-binds with maximized=false afterward.
      if (maximized) setMaximized(false)
    }

    const handleMouseUp = (): void => {
      setIsDragging(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ew-resize'

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [isDragging, setWidth, maximized, setMaximized])

  return { width, isDesktop, isDragging, handleMouseDown }
}
