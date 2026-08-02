import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, setupAuthInterceptor } from './api'
import { config } from '../config'
import toast from 'react-hot-toast'
import { isValidElement } from 'react'

vi.mock('../config', () => ({
  config: {
    apiUrl: 'http://localhost:8000',
  },
  isDevMode: false,
}))

// Mock the session-expiry store (the 401-final path parks requests in it)
const mockParkRequest = vi.fn()
vi.mock('../stores/sessionExpiryStore', () => ({
  useSessionExpiryStore: {
    getState: () => ({ parkRequest: mockParkRequest }),
  },
}))

// Mock react-hot-toast
vi.mock('react-hot-toast', () => ({
  default: {
    error: vi.fn(),
  },
}))

// Type for accessing internal axios interceptor handlers
interface AxiosInterceptorHandler {
  fulfilled?: (value: unknown) => unknown
  rejected?: (error: unknown) => unknown
}

/** Get the last registered response error handler. */
function getErrorHandler(): ((error: unknown) => unknown) | undefined {
  const handlers = (api.interceptors.response as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
  return handlers[handlers.length - 1]?.rejected
}

/** Get the last registered request fulfilled handler (stamps the sender identity). */
function getRequestHandler(): ((config: unknown) => unknown) | undefined {
  const handlers = (api.interceptors.request as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
  return handlers[handlers.length - 1]?.fulfilled
}

/** Build an unsigned JWT carrying the given `sub` claim (for identity-stamp tests). */
function fakeJwt(sub: string): string {
  const seg = (obj: unknown): string =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${seg({ alg: 'none' })}.${seg({ sub })}.sig`
}

/** Extract text content from a React element's props (shallow). */
function getToastText(): string {
  const call = vi.mocked(toast.error).mock.calls[0]
  if (!call) return ''
  const element = call[0]
  if (typeof element === 'string') return element
  // React element — extract children text recursively
  if (isValidElement(element) && element.props) {
    const children = (element.props as { children?: unknown }).children
    return Array.isArray(children)
      ? children.map((c: unknown) => {
          if (typeof c === 'string') return c
          if (isValidElement(c) && c.props) return (c.props as { children?: string }).children ?? ''
          return ''
        }).join('')
      : String(children ?? '')
  }
  return ''
}

/** Extract the href from the first anchor element in the toast JSX. */
function getToastLinkHref(): string | null {
  const call = vi.mocked(toast.error).mock.calls[0]
  if (!call) return null
  const element = call[0]
  if (!isValidElement(element) || !element.props) return null
  const children = (element.props as { children?: unknown }).children
  if (!Array.isArray(children)) return null
  for (const child of children) {
    if (isValidElement(child)) {
      const href = (child.props as { href?: string }).href
      if (href) return href
    }
  }
  return null
}

describe('api', () => {
  it('should have baseURL configured from config', () => {
    expect(api.defaults.baseURL).toBe(config.apiUrl)
  })

  it('should be an axios instance', () => {
    expect(api.get).toBeDefined()
    expect(api.post).toBeDefined()
    expect(api.put).toBeDefined()
    expect(api.delete).toBeDefined()
  })

  it('should have interceptors available', () => {
    expect(api.interceptors.request).toBeDefined()
    expect(api.interceptors.response).toBeDefined()
  })
})

describe('setupAuthInterceptor', () => {
  const mockOnAccountDeleted = vi.fn()
  const mockGetActiveUserId = vi.fn((): string | null => null)

  beforeEach(() => {
    vi.clearAllMocks()
    // clearAllMocks doesn't reset mockReturnValue, so re-default the active user
    // to "signed out" each test (guard tests override it explicitly).
    mockGetActiveUserId.mockReturnValue(null)
  })

  describe('402 response handling', () => {
    it('shows quota exceeded toast with pricing link', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mock402Error = {
        response: {
          status: 402,
          data: { error_code: 'QUOTA_EXCEEDED', resource: 'bookmark', limit: 10, current: 10 },
        },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock402Error)).rejects.toEqual(mock402Error)
      }

      expect(toast.error).toHaveBeenCalledWith(
        expect.anything(),
        { id: 'quota-exceeded' }
      )
      const text = getToastText()
      expect(text).toContain('10')
      expect(text).toContain('bookmarks')
      expect(text).toContain('Manage your plan')
      expect(getToastLinkHref()).toBe('/pricing')
    })

    it('does not show toast for non-quota 402', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mock402Error = {
        response: {
          status: 402,
          data: { error_code: 'SOMETHING_ELSE' },
        },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock402Error)).rejects.toEqual(mock402Error)
      }

      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe('429 response handling', () => {
    it('shows toast with retry-after and pricing link when 429 with header', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mock429Error = {
        response: {
          status: 429,
          headers: { 'retry-after': '30' },
        },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock429Error)).rejects.toEqual(mock429Error)
      }

      expect(toast.error).toHaveBeenCalledWith(
        expect.anything(),
        { id: 'rate-limit' }
      )
      const text = getToastText()
      expect(text).toContain('30 seconds')
      expect(text).toContain('Higher limits available')
      expect(getToastLinkHref()).toBe('/pricing')
    })

    it('shows provider-busy toast without pricing link or retry-after on 429 with llm_rate_limited', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      // Upstream LLM provider throttle — backend does not set Retry-After,
      // so the toast must not render a "wait N seconds" countdown.
      const mock429Error = {
        response: {
          status: 429,
          headers: {},
          data: { error_code: 'llm_rate_limited', detail: 'LLM provider rate limit exceeded.' },
        },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock429Error)).rejects.toEqual(mock429Error)
      }

      expect(toast.error).toHaveBeenCalledWith(
        expect.any(String),
        { id: 'rate-limit' }
      )
      const text = getToastText()
      expect(text).toContain('provider is busy')
      expect(text).not.toContain('Higher limits available')
      expect(text).not.toMatch(/\d+\s*seconds/)
      expect(text).not.toContain('undefined')
      expect(getToastLinkHref()).toBeNull()
    })

    it('shows generic toast with pricing link when 429 without retry-after', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mock429Error = {
        response: {
          status: 429,
          headers: {},
        },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock429Error)).rejects.toEqual(mock429Error)
      }

      expect(toast.error).toHaveBeenCalledWith(
        expect.anything(),
        { id: 'rate-limit' }
      )
      const text = getToastText()
      expect(text).toContain('try again later')
      expect(text).toContain('Higher limits available')
      expect(getToastLinkHref()).toBe('/pricing')
    })

    it('does not show toast for non-429 errors', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mock500Error = {
        response: { status: 500, headers: {} },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock500Error)).rejects.toEqual(mock500Error)
      }

      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe('401 response handling (one retry, then the session-expiry path)', () => {
    it('retries once with a fresh-minted token and resolves', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('fresh-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const requestSpy = vi.spyOn(api, 'request').mockResolvedValue({ data: 'ok' })
      const mock401Error = {
        response: { status: 401 },
        config: { headers: {} },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock401Error)).resolves.toEqual({ data: 'ok' })
      }

      expect(requestSpy).toHaveBeenCalledTimes(1)
      expect(mockGetToken).toHaveBeenCalledWith({ skipCache: true })
      expect(mockParkRequest).not.toHaveBeenCalled()
      requestSpy.mockRestore()
    })

    it('parks the request for re-auth when the retry also 401s — never rejects to a logout', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('fresh-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)
      mockParkRequest.mockResolvedValue({ data: 'after-reauth' })

      const errorHandler = getErrorHandler()
      // _retryAuth already set: this 401 is the retry's own failure.
      const mock401Error = {
        response: { status: 401 },
        config: { headers: {}, _retryAuth: true },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock401Error)).resolves.toEqual({ data: 'after-reauth' })
      }

      expect(mockParkRequest).toHaveBeenCalledTimes(1)
      // The parked retry callback must clear the retry marker and replay via api.request
      const retryFn = mockParkRequest.mock.calls[0]?.[0] as () => Promise<unknown>
      const requestSpy = vi.spyOn(api, 'request').mockResolvedValue({ data: 'replayed' })
      await expect(retryFn()).resolves.toEqual({ data: 'replayed' })
      expect(requestSpy).toHaveBeenCalledTimes(1)
      requestSpy.mockRestore()
    })

    it('parks the request when no token can be minted at all (no session)', async () => {
      const mockGetToken = vi.fn().mockResolvedValue(null)
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)
      mockParkRequest.mockResolvedValue({ data: 'after-reauth' })

      const errorHandler = getErrorHandler()
      const mock401Error = {
        response: { status: 401 },
        config: { headers: {} },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock401Error)).resolves.toEqual({ data: 'after-reauth' })
      }

      expect(mockGetToken).toHaveBeenCalledWith({ skipCache: true })
      expect(mockParkRequest).toHaveBeenCalledTimes(1)
    })
  })

  describe('account_deleted terminal 401', () => {
    it('hands off to onAccountDeleted and rejects — no refresh, no park', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('fresh-token')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mockError = {
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {} },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mockError)).rejects.toBe(mockError)
      }

      expect(mockOnAccountDeleted).toHaveBeenCalledTimes(1)
      expect(mockGetToken).not.toHaveBeenCalled() // no token refresh
      expect(mockParkRequest).not.toHaveBeenCalled() // never enters the expiry path
    })

    it('fires onAccountDeleted once across concurrent account_deleted 401s', async () => {
      setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const makeError = (): unknown => ({
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {} },
        isAxiosError: true,
      })

      if (errorHandler) {
        await Promise.allSettled([
          errorHandler(makeError()),
          errorHandler(makeError()),
          errorHandler(makeError()),
        ])
      }

      expect(mockOnAccountDeleted).toHaveBeenCalledTimes(1)
    })

    it('leaves an ordinary 401 (unrelated error_code) on the session-expiry path', async () => {
      const mockGetToken = vi.fn().mockResolvedValue(null)
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)
      mockParkRequest.mockResolvedValue({ data: 'after-reauth' })

      const errorHandler = getErrorHandler()
      const mockError = {
        response: { status: 401, data: { error_code: 'something_else' } },
        config: { headers: {} },
        isAxiosError: true,
      }

      if (errorHandler) {
        await errorHandler(mockError)
      }

      expect(mockOnAccountDeleted).not.toHaveBeenCalled()
      expect(mockParkRequest).toHaveBeenCalledTimes(1)
    })

    it('does NOT tear down when a different account is now active (cross-account guard)', async () => {
      mockGetActiveUserId.mockReturnValue('userB')
      setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mockError = {
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {}, _senderUserId: 'userA' },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mockError)).rejects.toBe(mockError)
      }

      expect(mockOnAccountDeleted).not.toHaveBeenCalled()
    })

    it('tears down when the response identity is still the active one', async () => {
      mockGetActiveUserId.mockReturnValue('userA')
      setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mockError = {
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {}, _senderUserId: 'userA' },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mockError)).rejects.toBe(mockError)
      }

      expect(mockOnAccountDeleted).toHaveBeenCalledTimes(1)
    })

    it('does NOT tear down when the sender is unverifiable and a user is active (fail closed)', async () => {
      mockGetActiveUserId.mockReturnValue('userB')
      setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)

      const errorHandler = getErrorHandler()
      const mockError = {
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {} }, // no _senderUserId — sender can't be verified
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mockError)).rejects.toBe(mockError)
      }

      expect(mockOnAccountDeleted).not.toHaveBeenCalled()
    })

    it('re-arms terminal handling for a later, different identity (latch is per-identity, not global)', async () => {
      setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)
      const errorHandler = getErrorHandler()

      // A is deleted while A is active → teardown fires.
      mockGetActiveUserId.mockReturnValue('userA')
      const errorA = {
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {}, _senderUserId: 'userA' },
        isAxiosError: true,
      }
      if (errorHandler) await expect(errorHandler(errorA)).rejects.toBe(errorA)

      // Later in the same SPA session, B is active and B is deleted → must fire
      // AGAIN (a global latch would silently no-op this).
      mockGetActiveUserId.mockReturnValue('userB')
      const errorB = {
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {}, _senderUserId: 'userB' },
        isAxiosError: true,
      }
      if (errorHandler) await expect(errorHandler(errorB)).rejects.toBe(errorB)

      expect(mockOnAccountDeleted).toHaveBeenCalledTimes(2)
    })

    it('retries a later response for the same identity if the first teardown throws', async () => {
      mockGetActiveUserId.mockReturnValue('userA')
      // First invocation throws (e.g. navigate fails); it must NOT latch the
      // identity off permanently — a later response for the same id retries.
      mockOnAccountDeleted.mockImplementationOnce(() => {
        throw new Error('nav boom')
      })
      setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)
      const errorHandler = getErrorHandler()
      const make = (): unknown => ({
        response: { status: 401, data: { error_code: 'account_deleted' } },
        config: { headers: {}, _senderUserId: 'userA' },
        isAxiosError: true,
      })

      const e1 = make()
      const e2 = make()
      if (errorHandler) {
        await expect(errorHandler(e1)).rejects.toBe(e1)
        await expect(errorHandler(e2)).rejects.toBe(e2)
      }

      expect(mockOnAccountDeleted).toHaveBeenCalledTimes(2)
    })
  })

  describe('request identity stamp (cross-account guard input)', () => {
    it('stamps _senderUserId from the attached token sub, not the active user', async () => {
      // Token belongs to A, but the active user has since switched to B; the
      // stamp must reflect the TOKEN (A), so a stale A response never matches B.
      const mockGetToken = vi.fn().mockResolvedValue(fakeJwt('userA'))
      mockGetActiveUserId.mockReturnValue('userB')
      setupAuthInterceptor(mockGetToken, mockOnAccountDeleted, mockGetActiveUserId)

      const requestHandler = getRequestHandler()
      const config: { headers: Record<string, string>; _senderUserId?: string | null } = { headers: {} }
      if (requestHandler) {
        await requestHandler(config)
      }

      expect(config._senderUserId).toBe('userA')
    })
  })

  describe('interceptor lifecycle', () => {
    it('returns a cleanup that ejects the interceptor (no stacking on re-setup)', () => {
      const cleanup = setupAuthInterceptor(vi.fn(), mockOnAccountDeleted, mockGetActiveUserId)
      expect(getErrorHandler()).toBeDefined()
      cleanup()
      expect(getErrorHandler()).toBeUndefined()
    })
  })
})
