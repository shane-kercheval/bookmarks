/**
 * Tests for the in-app save route that completes the public "Save to Tiddly"
 * flow after consent.
 *
 * The route must: wait for consent to be ready before firing the clone, fire it
 * exactly once, treat a 451 as the consent detour (not a hard failure), land
 * hard failures on the content list, and fall back to the content list if the
 * consent check never resolves.
 *
 * The full cross-component handoff (public in-place 451 → useSavePublicItem
 * redirects here → consent → save) is covered unit-side by design: the hook test
 * proves the 451 redirect targets this route, and the cases below prove the route
 * fires after consent. No separate integration test exercises the whole chain.
 */
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest'
import { render, act } from '@testing-library/react'
import toast from 'react-hot-toast'
import { SaveSharedRedirect } from './SaveSharedRedirect'

// Auth/consent readiness is driven by these module-level mutables, flipped per
// test to model the optimistic-then-resolved consent sequence.
let mockIsDevMode = false
vi.mock('../config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../config')>()
  return { ...actual, get isDevMode() { return mockIsDevMode } }
})

let mockNeedsConsent: boolean | null = false
vi.mock('../stores/consentStore', () => ({
  useConsentStore: (selector?: (state: Record<string, unknown>) => unknown) => {
    const state = { needsConsent: mockNeedsConsent }
    return selector ? selector(state) : state
  },
}))

const mockMutate = vi.fn()
let mockSaveState: { isError: boolean; error: unknown } = { isError: false, error: undefined }
vi.mock('../hooks/useSavePublicItem', () => ({
  useSavePublicItem: () => ({ mutate: mockMutate, isError: mockSaveState.isError, error: mockSaveState.error }),
}))

const mockNavigate = vi.fn()
let mockParams: { type?: string; token?: string } = { type: 'notes', token: 'tok' }
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate, useParams: () => mockParams }
})

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }))
vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      isAxiosError: (e: unknown) => !!(e as { isAxiosError?: boolean })?.isAxiosError,
    },
  }
})

const mockToastError = toast.error as Mock

function axiosError(status: number): unknown {
  return { isAxiosError: true, response: { status } }
}

describe('SaveSharedRedirect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mockIsDevMode = false
    mockNeedsConsent = false
    mockSaveState = { isError: false, error: undefined }
    mockParams = { type: 'notes', token: 'tok' }
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('does not fire the save until consent is ready, then fires once', () => {
    mockNeedsConsent = null // consent check in flight (not dev mode)
    const { rerender } = render(<SaveSharedRedirect />)
    expect(mockMutate).not.toHaveBeenCalled()

    mockNeedsConsent = false // consent resolved (already-consented or just accepted)
    act(() => { rerender(<SaveSharedRedirect />) })
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('fires exactly once across re-renders (ref-guarded)', () => {
    const { rerender } = render(<SaveSharedRedirect />)
    act(() => { rerender(<SaveSharedRedirect />) })
    act(() => { rerender(<SaveSharedRedirect />) })
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('fires immediately in dev mode (consent bypassed, needsConsent stays null)', () => {
    mockIsDevMode = true
    mockNeedsConsent = null
    render(<SaveSharedRedirect />)
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('lands a hard failure (409 conflict) on the content list', () => {
    mockSaveState = { isError: true, error: axiosError(409) }
    render(<SaveSharedRedirect />)
    expect(mockNavigate).toHaveBeenCalledWith('/app/content', { replace: true })
  })

  it('treats a 451 as the consent detour — does not bounce to the content list', () => {
    mockSaveState = { isError: true, error: axiosError(451) }
    render(<SaveSharedRedirect />)
    expect(mockNavigate).not.toHaveBeenCalledWith('/app/content', { replace: true })
  })

  it('redirects a garbled type to the content list without firing the save', () => {
    mockParams = { type: 'widgets', token: 'tok' }
    render(<SaveSharedRedirect />)
    expect(mockNavigate).toHaveBeenCalledWith('/app/content', { replace: true })
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('falls back to the content list if the consent check never resolves', () => {
    mockNeedsConsent = null // never settles
    render(<SaveSharedRedirect />)
    expect(mockMutate).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(15_000) })
    expect(mockToastError).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith('/app/content', { replace: true })
  })

  it('clears the readiness timer on unmount (the consent-dialog detour)', () => {
    // The real new-user path: mount with consent pending (timer armed) → the
    // ConsentDialog mounts and this route unmounts while the user reads Terms
    // (possibly >15s) → accept → remount. The pending timer must not fire after
    // unmount, or it would yank the user off the dialog to the content list.
    mockNeedsConsent = null
    const { unmount } = render(<SaveSharedRedirect />)
    expect(mockMutate).not.toHaveBeenCalled()

    unmount()
    act(() => { vi.advanceTimersByTime(15_000) })
    expect(mockNavigate).not.toHaveBeenCalledWith('/app/content', { replace: true })
    expect(mockToastError).not.toHaveBeenCalled()
  })

  it('does not fire the timeout once the save is in flight', () => {
    render(<SaveSharedRedirect />) // consentReady, fires immediately
    expect(mockMutate).toHaveBeenCalledTimes(1)

    act(() => { vi.advanceTimersByTime(15_000) })
    // No timeout navigation — the in-flight clone is left to resolve on its own.
    expect(mockNavigate).not.toHaveBeenCalledWith('/app/content', { replace: true })
    expect(mockToastError).not.toHaveBeenCalled()
  })
})
