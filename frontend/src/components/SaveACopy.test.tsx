/**
 * Tests for the auth-aware "Save a copy" control.
 *
 * Overrides the global useAuthStatus mock (test/setup.ts) per case to exercise
 * the three branches: initializing, authenticated, anonymous.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { SaveACopy } from './SaveACopy'

// `mock`-prefixed so vitest allows referencing it inside the hoisted factory.
let mockAuthStatus: {
  isAuthenticated: boolean
  isLoading: boolean
  error: Error | null
  userId: string | null
  userEmail: string | null
} = { isAuthenticated: true, isLoading: false, error: null, userId: 'u', userEmail: null }
vi.mock('../hooks/useAuthStatus', () => ({ useAuthStatus: () => mockAuthStatus }))

const mockMutate = vi.fn()
vi.mock('../hooks/useSavePublicItem', () => ({
  useSavePublicItem: () => ({ mutate: mockMutate, isPending: false }),
}))

const mockLogin = vi.fn()
vi.mock('../hooks/useAuthActions', () => ({
  useAuthActions: () => ({ login: mockLogin, logout: vi.fn() }),
}))

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <SaveACopy type="notes" token="tok" />
    </MemoryRouter>
  )
}

describe('SaveACopy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthStatus = { isAuthenticated: true, isLoading: false, error: null, userId: 'u', userEmail: null }
  })

  it('renders a neutral placeholder (no button) while auth is initializing', () => {
    mockAuthStatus = { isAuthenticated: false, isLoading: true, error: null, userId: null, userEmail: null }
    renderAt('/shared/notes/tok')
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('authenticated: shows "Save a copy" and clones on click', async () => {
    renderAt('/shared/notes/tok')
    await userEvent.click(screen.getByRole('button', { name: 'Save to Tiddly' }))
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('anonymous: shows sign-in and returns to the in-app save route after login', async () => {
    // returnTo points at the in-app save route (not the shared URL) so the
    // clone can fire automatically after sign-up rather than leaving the user
    // back on the public page having to click Save again.
    mockAuthStatus = { isAuthenticated: false, isLoading: false, error: null, userId: null, userEmail: null }
    renderAt('/shared/notes/tok')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in to save' }))
    expect(mockLogin).toHaveBeenCalledWith({
      mode: 'login',
      returnTo: '/app/save-shared/notes/tok',
    })
  })
})
