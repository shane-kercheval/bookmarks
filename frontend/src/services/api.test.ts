import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, setupAuthInterceptor } from './api'
import { config } from '../config'
import { useConsentStore } from '../stores/consentStore'
import toast from 'react-hot-toast'

// Mock the consent store
vi.mock('../stores/consentStore', () => ({
  useConsentStore: {
    getState: vi.fn(),
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
  const mockHandleConsentRequired = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useConsentStore.getState).mockReturnValue({
      consent: null,
      needsConsent: null,
      currentPrivacyVersion: null,
      currentTermsVersion: null,
      isLoading: false,
      error: null,
      reset: vi.fn(),
      checkConsent: vi.fn(),
      handleConsentRequired: mockHandleConsentRequired,
      recordConsent: vi.fn(),
    })
  })

  describe('451 response handling', () => {
    it('calls handleConsentRequired when 451 is received', async () => {
      // Set up the interceptor
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      const mockOnAuthError = vi.fn()
      setupAuthInterceptor(mockGetToken, mockOnAuthError)

      // Access internal handlers (cast to any to access internal structure)
      const handlers = (api.interceptors.response as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
      const errorHandler = handlers[handlers.length - 1]?.rejected

      const mock451Error = {
        response: { status: 451 },
        isAxiosError: true,
      }

      // The handler should reject the promise but still call handleConsentRequired
      if (errorHandler) {
        await expect(errorHandler(mock451Error)).rejects.toEqual(mock451Error)
      }

      expect(mockHandleConsentRequired).toHaveBeenCalledTimes(1)
    })

    it('does not call handleConsentRequired for non-451 errors', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      const mockOnAuthError = vi.fn()
      setupAuthInterceptor(mockGetToken, mockOnAuthError)

      // Access internal handlers (cast to any to access internal structure)
      const handlers = (api.interceptors.response as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
      const errorHandler = handlers[handlers.length - 1]?.rejected

      const mock500Error = {
        response: { status: 500 },
        isAxiosError: true,
      }

      if (errorHandler) {
        await expect(errorHandler(mock500Error)).rejects.toEqual(mock500Error)
      }

      expect(mockHandleConsentRequired).not.toHaveBeenCalled()
    })
  })

  describe('429 response handling', () => {
    it('shows toast with retry-after when 429 is received with header', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      const mockOnAuthError = vi.fn()
      setupAuthInterceptor(mockGetToken, mockOnAuthError)

      const handlers = (api.interceptors.response as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
      const errorHandler = handlers[handlers.length - 1]?.rejected

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
        'Too many requests. Please wait 30 seconds.',
        { id: 'rate-limit' }
      )
    })

    it('shows generic toast when 429 is received without retry-after', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      const mockOnAuthError = vi.fn()
      setupAuthInterceptor(mockGetToken, mockOnAuthError)

      const handlers = (api.interceptors.response as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
      const errorHandler = handlers[handlers.length - 1]?.rejected

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
        'Too many requests. Please try again later.',
        { id: 'rate-limit' }
      )
    })

    it('does not show toast for non-429 errors', async () => {
      const mockGetToken = vi.fn().mockResolvedValue('test-token')
      const mockOnAuthError = vi.fn()
      setupAuthInterceptor(mockGetToken, mockOnAuthError)

      const handlers = (api.interceptors.response as unknown as { handlers: AxiosInterceptorHandler[] }).handlers
      const errorHandler = handlers[handlers.length - 1]?.rejected

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
})
