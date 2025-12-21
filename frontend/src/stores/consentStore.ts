/**
 * Zustand store for user consent management.
 * Manages consent state and checking with in-memory caching.
 *
 * NOTE: Uses in-memory cache only (no localStorage) to avoid stale consent
 * status after policy updates. One API call per session is acceptable performance.
 *
 * Version checking is handled server-side for consistency and maintainability.
 * Current required versions are fetched from the backend to ensure single source of truth.
 */
import { create } from 'zustand'
import type { ConsentResponse } from '../services/api'
import { checkConsentStatus, recordMyConsent } from '../services/api'

interface ConsentState {
  consent: ConsentResponse | null
  needsConsent: boolean | null  // null = not checked yet, true/false after check
  currentPrivacyVersion: string | null  // fetched from backend
  currentTermsVersion: string | null    // fetched from backend
  isLoading: boolean
  error: string | null
}

interface ConsentActions {
  checkConsent: () => Promise<void>
  recordConsent: () => Promise<void>
  reset: () => void
  /** Handle 451 response - immediately show dialog and fetch new versions */
  handleConsentRequired: () => void
}

type ConsentStore = ConsentState & ConsentActions

export const useConsentStore = create<ConsentStore>((set, get) => ({
  // State
  consent: null,
  needsConsent: null,
  currentPrivacyVersion: null,
  currentTermsVersion: null,
  isLoading: false,
  error: null,

  // Actions
  /**
   * Check if user needs to consent (or re-consent).
   * Caches result in memory for the session.
   *
   * Version checking is done server-side - backend compares stored consent
   * versions against current policy versions. Current versions are fetched
   * from backend to ensure single source of truth.
   */
  checkConsent: async () => {
    // If already checked this session or currently checking, don't check again
    if (get().needsConsent !== null || get().isLoading) {
      return
    }

    set({ isLoading: true, error: null })
    try {
      const status = await checkConsentStatus()

      set({
        consent: status.current_consent,
        needsConsent: status.needs_consent,
        currentPrivacyVersion: status.current_privacy_version,
        currentTermsVersion: status.current_terms_version,
        isLoading: false
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to check consent'
      set({ isLoading: false, error: message })
    }
  },

  /**
   * Record user's consent with current policy versions from backend.
   */
  recordConsent: async () => {
    const { currentPrivacyVersion, currentTermsVersion } = get()

    if (!currentPrivacyVersion || !currentTermsVersion) {
      throw new Error('Policy versions not loaded. Call checkConsent first.')
    }

    set({ isLoading: true, error: null })
    try {
      const consent = await recordMyConsent({
        privacy_policy_version: currentPrivacyVersion,
        terms_of_service_version: currentTermsVersion,
      })

      set({
        consent,
        needsConsent: false,
        isLoading: false
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to record consent'
      set({ isLoading: false, error: message })
      throw err  // Re-throw so UI can handle
    }
  },

  /**
   * Reset consent state (e.g., on logout).
   */
  reset: () => {
    set({
      consent: null,
      needsConsent: null,
      currentPrivacyVersion: null,
      currentTermsVersion: null,
      isLoading: false,
      error: null,
    })
  },

  /**
   * Handle 451 response - immediately show dialog and fetch new versions.
   * Called by the API interceptor when backend returns 451.
   *
   * Unlike reset() + checkConsent(), this:
   * 1. Immediately sets needsConsent=true to show dialog
   * 2. Only fetches new versions if not already loading
   * 3. Prevents race conditions from multiple 451s
   */
  handleConsentRequired: () => {
    const state = get()

    // If already showing consent dialog or loading, skip
    if (state.needsConsent === true || state.isLoading) {
      return
    }

    // Immediately show consent dialog
    set({ needsConsent: true, isLoading: true, error: null })

    // Fetch new policy versions in background
    checkConsentStatus()
      .then((status) => {
        set({
          currentPrivacyVersion: status.current_privacy_version,
          currentTermsVersion: status.current_terms_version,
          isLoading: false,
        })
      })
      .catch(() => {
        // If fetch fails, dialog is still shown - user can retry
        set({ isLoading: false })
      })
  },
}))
