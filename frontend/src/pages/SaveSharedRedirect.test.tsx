/**
 * Tests for the in-app save route that completes the public "Save to Tiddly"
 * flow after sign-in.
 *
 * The route must fire the clone exactly once on mount, land hard failures on
 * the content list, and reject a garbled URL without firing the (non-idempotent)
 * save at all.
 *
 * This file previously also covered a consent-readiness gate, a 15s fallback
 * timeout guarding that gate, and 451-as-detour handling. All three were
 * removed with the consent gate (2026-08-01): the route renders under
 * ProtectedRoute, which withholds its Outlet until auth resolves, so there is
 * nothing left to wait for and no timer to guard.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { render } from '@testing-library/react'
import toast from 'react-hot-toast'
import { SaveSharedRedirect } from './SaveSharedRedirect'

const mockMutate = vi.fn()
let mockSaveState: { isError: boolean } = { isError: false }
vi.mock('../hooks/useSavePublicItem', () => ({
  useSavePublicItem: () => ({ mutate: mockMutate, isError: mockSaveState.isError }),
}))

const mockNavigate = vi.fn()
let mockParams: { type?: string; token?: string } = { type: 'notes', token: 'tok' }
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate, useParams: () => mockParams }
})

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }))

const mockToastError = toast.error as Mock

describe('SaveSharedRedirect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSaveState = { isError: false }
    mockParams = { type: 'notes', token: 'tok' }
  })

  it('fires the save on mount', () => {
    render(<SaveSharedRedirect />)

    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('fires exactly once across re-renders (ref-guarded)', () => {
    // The clone is not idempotent — a StrictMode double-invoke or an ordinary
    // re-render must not produce a second copy.
    const { rerender } = render(<SaveSharedRedirect />)
    rerender(<SaveSharedRedirect />)
    rerender(<SaveSharedRedirect />)

    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('lands a hard failure (409 conflict) on the content list', () => {
    // The hook owns the toast; this route only picks the landing page.
    mockSaveState = { isError: true }

    render(<SaveSharedRedirect />)

    expect(mockNavigate).toHaveBeenCalledWith('/app/content', { replace: true })
    expect(mockToastError).not.toHaveBeenCalled()
  })

  it('redirects a garbled type to the content list without firing the save', () => {
    mockParams = { type: 'widgets', token: 'tok' }

    render(<SaveSharedRedirect />)

    expect(mockNavigate).toHaveBeenCalledWith('/app/content', { replace: true })
    expect(mockMutate).not.toHaveBeenCalled()
  })
})
