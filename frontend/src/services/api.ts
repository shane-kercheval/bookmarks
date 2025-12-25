import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import toast from 'react-hot-toast'
import { config, isDevMode } from '../config'
import { useConsentStore } from '../stores/consentStore'

/**
 * Axios instance configured with the API base URL.
 * Auth interceptors are set up separately via setupAuthInterceptor.
 */
export const api = axios.create({
  baseURL: config.apiUrl,
})

/**
 * Token getter function type - provided by Auth0 context.
 */
type GetAccessTokenFn = () => Promise<string>

/**
 * Auth error handler function type - called when 401 is received.
 */
type OnAuthErrorFn = () => void

/**
 * Consent API types
 */
export interface ConsentResponse {
  id: number
  user_id: number
  consented_at: string
  privacy_policy_version: string
  terms_of_service_version: string
  ip_address: string | null
  user_agent: string | null
}

export interface ConsentCreate {
  privacy_policy_version: string
  terms_of_service_version: string
}

export interface ConsentStatus {
  needs_consent: boolean
  current_consent: ConsentResponse | null
  current_privacy_version: string
  current_terms_version: string
}

export interface PolicyVersions {
  privacy_policy_version: string
  terms_of_service_version: string
}

/**
 * Sets up auth interceptors on the API instance.
 * Should be called once when the Auth0 context is available.
 *
 * @param getAccessToken - Function to get the current access token
 * @param onAuthError - Function to call when authentication fails (e.g., logout)
 */
export function setupAuthInterceptor(
  getAccessToken: GetAccessTokenFn,
  onAuthError: OnAuthErrorFn
): void {
  // Request interceptor - add auth token (production only)
  api.interceptors.request.use(
    async (requestConfig: InternalAxiosRequestConfig) => {
      if (!isDevMode) {
        try {
          const token = await getAccessToken()
          requestConfig.headers.Authorization = `Bearer ${token}`
        } catch {
          // Token fetch failed - let the request proceed without auth
          // The 401 response interceptor will handle it
        }
      }
      return requestConfig
    },
    (error: AxiosError) => Promise.reject(error)
  )

  // Response interceptor - handle auth, consent, and rate limit errors
  api.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      if (error.response?.status === 401 && !isDevMode) {
        // Token expired or invalid - trigger logout/re-login
        onAuthError()
      }
      if (error.response?.status === 429) {
        // Rate limit exceeded - show user-friendly message
        const retryAfter = error.response.headers['retry-after']
        const message = retryAfter
          ? `Too many requests. Please wait ${retryAfter} seconds.`
          : 'Too many requests. Please try again later.'
        toast.error(message, { id: 'rate-limit' }) // id prevents duplicate toasts
      }
      if (error.response?.status === 451) {
        // Consent required - show dialog immediately and fetch new versions
        useConsentStore.getState().handleConsentRequired()
      }
      return Promise.reject(error)
    }
  )
}

/**
 * Consent API Methods
 */

/**
 * Check if user needs to consent.
 * This is the recommended endpoint - never returns 404.
 *
 * Returns:
 * - needs_consent: true if user needs to accept/re-accept terms
 * - current_consent: existing consent record (if any)
 */
export async function checkConsentStatus(): Promise<ConsentStatus> {
  const response = await api.get<ConsentStatus>('/consent/status')
  return response.data
}

/**
 * Record or update the current user's consent.
 * Creates a new consent record if none exists, or updates the existing one.
 */
export async function recordMyConsent(
  data: ConsentCreate
): Promise<ConsentResponse> {
  const response = await api.post<ConsentResponse>('/consent/me', data)
  return response.data
}

/**
 * Get current policy versions (public endpoint, no auth required).
 * Used by public pages to display version dates.
 */
export async function getPolicyVersions(): Promise<PolicyVersions> {
  // Use axios directly instead of api instance to avoid auth interceptors
  const response = await axios.get<PolicyVersions>(`${config.apiUrl}/consent/versions`)
  return response.data
}
