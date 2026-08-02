import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuthProvider } from './AuthProvider'
import { setupAuthInterceptor } from '../services/api'
import { useAuth, useClerk, useUser } from '@clerk/clerk-react'
import { useAuthStatus } from '../hooks/useAuthStatus'
import { useAuthActions } from '../hooks/useAuthActions'
import { queryClient } from '../queryClient'
import { useAIStore } from '../stores/aiStore'
import { useSessionExpiryStore } from '../stores/sessionExpiryStore'

// The global setup (test/setup.ts) mocks the seam hooks module-wide; these
// tests exist to verify the REAL seam bridge (seam call -> SDK call), so the
// real modules must be used — otherwise the probe below would silently read
// the global stub and pass regardless of the bridge's wiring. The assertion
// values are chosen to be impossible under the stub (its login is a no-op and
// its userId is 'test-user-id'), so a regression of this unmock fails loudly.
vi.unmock('../hooks/useAuthStatus')
vi.unmock('../hooks/useAuthActions')

const mockGetToken = vi.fn().mockResolvedValue('token')
const mockSignOut = vi.fn()
const mockOpenSignIn = vi.fn()
const mockOpenSignUp = vi.fn()

let mockIsDevMode = false

vi.mock('../config', () => ({
  config: {
    clerk: {
      publishableKey: 'pk_test_abc',
    },
  },
  get isDevMode() {
    return mockIsDevMode
  },
}))

vi.mock('../services/api', () => ({
  setupAuthInterceptor: vi.fn(),
}))

vi.mock('../queryClient', () => ({
  queryClient: { clear: vi.fn() },
}))

const clerkProviderProps = vi.fn()
vi.mock('@clerk/clerk-react', () => ({
  ClerkProvider: (props: { children: ReactNode }) => {
    clerkProviderProps(props)
    return <>{props.children}</>
  },
  useAuth: vi.fn(),
  useClerk: vi.fn(),
  useUser: vi.fn(),
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => mockNavigate,
}))

// Renders what the real seam delivers to a consuming component: status as
// text, actions as buttons — so tests exercise the seam the way call sites do.
function SeamProbe(): ReactNode {
  const status = useAuthStatus()
  const { login, logout } = useAuthActions()
  return (
    <div>
      <span data-testid="user-id">{String(status.userId)}</span>
      <span data-testid="user-email">{String(status.userEmail)}</span>
      <span data-testid="is-authenticated">{String(status.isAuthenticated)}</span>
      <span data-testid="is-loading">{String(status.isLoading)}</span>
      <span data-testid="error">{status.error ? status.error.message : 'null'}</span>
      <button onClick={() => login({ mode: 'signup', returnTo: '/app/save-shared/notes/tok' })}>
        signup-with-return
      </button>
      <button onClick={() => login()}>default-login</button>
      <button onClick={() => logout()}>seam-logout</button>
    </div>
  )
}

function renderWithProbe(): void {
  render(
    <MemoryRouter>
      <AuthProvider>
        <SeamProbe />
      </AuthProvider>
    </MemoryRouter>
  )
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsDevMode = false
    vi.mocked(useAuth).mockReturnValue({
      isLoaded: true,
      isSignedIn: true,
      userId: 'user_clerk123',
      getToken: mockGetToken,
    } as unknown as ReturnType<typeof useAuth>)
    vi.mocked(useUser).mockReturnValue({
      user: { primaryEmailAddress: { emailAddress: 'real@example.com' } },
    } as unknown as ReturnType<typeof useUser>)
    vi.mocked(useClerk).mockReturnValue({
      openSignIn: mockOpenSignIn,
      openSignUp: mockOpenSignUp,
      signOut: mockSignOut,
      status: 'ready',
    } as unknown as ReturnType<typeof useClerk>)
  })

  it('wires the interceptor to getToken, passing skipCache through on retry', async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <div>child</div>
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() => expect(setupAuthInterceptor).toHaveBeenCalledTimes(1))
    const getAccessToken = vi.mocked(setupAuthInterceptor).mock.calls[0]?.[0]

    await getAccessToken?.({ skipCache: true })

    expect(mockGetToken).toHaveBeenCalledWith({ skipCache: true })
  })

  describe('account-deletion terminal teardown', () => {
    afterEach(() => {
      // Reset the real stores/localStorage this teardown mutates so it can't leak.
      useAIStore.getState().clearAllKeys()
      useSessionExpiryStore.getState().reset()
      useSessionExpiryStore.getState().clearDeliberateLogout()
      useSessionExpiryStore.setState({ accountDeleted: false })
      localStorage.clear()
    })

    /** Render and return the onAccountDeleted callback the interceptor was wired with. */
    async function getOnAccountDeleted(): Promise<() => void> {
      render(
        <MemoryRouter>
          <AuthProvider><div /></AuthProvider>
        </MemoryRouter>
      )
      await waitFor(() => expect(setupAuthInterceptor).toHaveBeenCalled())
      const fn = vi.mocked(setupAuthInterceptor).mock.calls[0]?.[1]
      expect(fn).toBeTypeOf('function')
      return fn as () => void
    }

    it("clears the deleted user's BYOK keys + drafts and navigates to the terminal page", async () => {
      useAIStore.getState().setApiKey('suggestions', 'sk-secret')
      localStorage.setItem('tiddly:draft:note:x', 'draft')

      const onAccountDeleted = await getOnAccountDeleted()
      onAccountDeleted()

      // Terminal flag set (exempts the unsaved-changes blocker) before navigation.
      expect(useSessionExpiryStore.getState().accountDeleted).toBe(true)
      expect(mockNavigate).toHaveBeenCalledWith('/account-deleted', { replace: true })
      expect(useAIStore.getState().useCaseConfigs.suggestions.apiKey).toBeNull()
      expect(localStorage.getItem('tiddly:draft:note:x')).toBeNull()
      expect(queryClient.clear).toHaveBeenCalled()
      // Sign-out pinned to the terminal page so Clerk can't redirect off it.
      expect(mockSignOut).toHaveBeenCalledWith({ redirectUrl: '/account-deleted' })
    })

    it('navigates to the terminal page even when sign-out rejects', async () => {
      mockSignOut.mockRejectedValueOnce(new Error('signout failed'))

      const onAccountDeleted = await getOnAccountDeleted()
      onAccountDeleted()

      expect(mockNavigate).toHaveBeenCalledWith('/account-deleted', { replace: true })
    })

    it('still navigates when a cleanup step throws (best-effort teardown)', async () => {
      vi.mocked(queryClient.clear).mockImplementationOnce(() => {
        throw new Error('storage unavailable')
      })

      const onAccountDeleted = await getOnAccountDeleted()
      onAccountDeleted()

      expect(mockNavigate).toHaveBeenCalledWith('/account-deleted', { replace: true })
    })
  })

  it('router bridge treats same-location navigation as a no-op', () => {
    // The expiry dialog pins its post-re-auth redirect to the current URL so
    // nothing moves; an actual navigate() there would trip the
    // unsaved-changes blocker (caught live in the M3 rehearsal).
    renderWithProbe()
    const props = clerkProviderProps.mock.calls.at(-1)?.[0] as {
      routerPush: (to: string) => void
      routerReplace: (to: string) => void
    }
    const here = window.location.pathname + window.location.search

    props.routerPush(here)
    props.routerReplace(here)
    // Clerk sometimes passes absolute URLs — same-location must match those too.
    props.routerPush(window.location.origin + here)
    expect(mockNavigate).not.toHaveBeenCalled()

    props.routerPush('/app/content')
    expect(mockNavigate).toHaveBeenCalledWith('/app/content')
    // Absolute URLs to a DIFFERENT location navigate path-relative.
    props.routerPush(window.location.origin + '/app/other')
    expect(mockNavigate).toHaveBeenCalledWith('/app/other')
    props.routerReplace('/somewhere')
    expect(mockNavigate).toHaveBeenCalledWith('/somewhere', { replace: true })
  })

  describe('seam bridge (the only module allowed to touch the SDK)', () => {
    it('login({ mode: signup, returnTo }) opens the signup modal with a sanitized redirect', async () => {
      renderWithProbe()
      await userEvent.click(screen.getByRole('button', { name: 'signup-with-return' }))
      expect(mockOpenSignUp).toHaveBeenCalledWith({
        forceRedirectUrl: '/app/save-shared/notes/tok',
      })
      expect(mockOpenSignIn).not.toHaveBeenCalled()
    })

    it('login() opens the sign-in modal with no redirect override', async () => {
      // No forceRedirectUrl: Clerk's default post-login destination is `/`,
      // where the landing page redirects signed-in users into the app.
      renderWithProbe()
      await userEvent.click(screen.getByRole('button', { name: 'default-login' }))
      expect(mockOpenSignIn).toHaveBeenCalledWith({})
      expect(mockOpenSignUp).not.toHaveBeenCalled()
    })

    it('logout() owns ALL teardown: query cache and Clerk sign-out', async () => {
      // The session-expiry path must never do any of this (plan M3 step 7) —
      // deliberate logout is the only place state is destroyed.
      renderWithProbe()
      await userEvent.click(screen.getByRole('button', { name: 'seam-logout' }))
      expect(queryClient.clear).toHaveBeenCalledTimes(1)
      expect(mockSignOut).toHaveBeenCalledWith({
        redirectUrl: window.location.origin,
      })
    })

    it('status derives userId and userEmail from the Clerk user', () => {
      renderWithProbe()
      // Values deliberately differ from the global stub ('test-user-id' /
      // 'test-user@example.com') so this cannot pass against the mock.
      expect(screen.getByTestId('user-id').textContent).toBe('user_clerk123')
      expect(screen.getByTestId('user-email').textContent).toBe('real@example.com')
      expect(screen.getByTestId('is-authenticated').textContent).toBe('true')
      expect(screen.getByTestId('is-loading').textContent).toBe('false')
    })

    it('reports loading until Clerk has loaded', () => {
      vi.mocked(useAuth).mockReturnValue({
        isLoaded: false,
        isSignedIn: undefined,
        userId: undefined,
        getToken: mockGetToken,
      } as unknown as ReturnType<typeof useAuth>)
      vi.mocked(useUser).mockReturnValue({
        user: null,
      } as unknown as ReturnType<typeof useUser>)
      renderWithProbe()
      expect(screen.getByTestId('is-loading').textContent).toBe('true')
      expect(screen.getByTestId('is-authenticated').textContent).toBe('false')
    })

    it('surfaces a hard init failure as an error, with loading forced off', () => {
      // clerk.status === 'error' must reach ProtectedRoute's recovery screen;
      // isLoading forced false so the loading branch cannot mask it (isLoaded
      // never becomes true on a failed init).
      vi.mocked(useAuth).mockReturnValue({
        isLoaded: false,
        isSignedIn: undefined,
        userId: undefined,
        getToken: mockGetToken,
      } as unknown as ReturnType<typeof useAuth>)
      vi.mocked(useUser).mockReturnValue({ user: null } as unknown as ReturnType<typeof useUser>)
      vi.mocked(useClerk).mockReturnValue({
        openSignIn: mockOpenSignIn,
        openSignUp: mockOpenSignUp,
        signOut: mockSignOut,
        status: 'error',
      } as unknown as ReturnType<typeof useClerk>)
      renderWithProbe()
      expect(screen.getByTestId('is-loading').textContent).toBe('false')
      expect(screen.getByTestId('error').textContent).toContain('failed to load')
    })

    it("treats 'degraded' as non-fatal — the app still functions", () => {
      vi.mocked(useClerk).mockReturnValue({
        openSignIn: mockOpenSignIn,
        openSignUp: mockOpenSignUp,
        signOut: mockSignOut,
        status: 'degraded',
      } as unknown as ReturnType<typeof useClerk>)
      renderWithProbe()
      expect(screen.getByTestId('error').textContent).toBe('null')
      expect(screen.getByTestId('is-authenticated').textContent).toBe('true')
    })

    it('dev mode: the seam resolves everywhere with no-op actions', async () => {
      // This property is what let call sites drop their "SDK only in
      // production" isolation wrappers — guard it.
      mockIsDevMode = true
      renderWithProbe()
      expect(screen.getByTestId('is-authenticated').textContent).toBe('true')
      expect(screen.getByTestId('user-id').textContent).toBe('dev-user')
      await userEvent.click(screen.getByRole('button', { name: 'default-login' }))
      await userEvent.click(screen.getByRole('button', { name: 'seam-logout' }))
      expect(mockOpenSignIn).not.toHaveBeenCalled()
      expect(mockSignOut).not.toHaveBeenCalled()
    })
  })
})
