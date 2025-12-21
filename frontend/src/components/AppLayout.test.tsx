/**
 * Tests for AppLayout component.
 * Tests consent enforcement behavior.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AppLayout } from './AppLayout'
import { useConsentStore } from '../stores/consentStore'
import * as config from '../config'

// Mock the consent store
vi.mock('../stores/consentStore', () => ({
  useConsentStore: vi.fn(),
}))

// Mock the config module
vi.mock('../config', () => ({
  isDevMode: false,
}))

// Mock ConsentDialog to avoid testing its internals here
vi.mock('./ConsentDialog', () => ({
  ConsentDialog: () => <div data-testid="consent-dialog">Consent Dialog</div>,
}))

const mockUseConsentStore = useConsentStore as unknown as ReturnType<typeof vi.fn>

describe('AppLayout', () => {
  const defaultMockState = {
    needsConsent: null,
    isLoading: false,
    checkConsent: vi.fn().mockResolvedValue(undefined),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    // Reset isDevMode to false by default
    vi.mocked(config).isDevMode = false
    mockUseConsentStore.mockReturnValue(defaultMockState)
  })

  const renderAppLayout = () => {
    return render(
      <MemoryRouter initialEntries={['/app']}>
        <Routes>
          <Route path="/app" element={<AppLayout />}>
            <Route index element={<div data-testid="child-content">App Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
  }

  describe('consent checking', () => {
    it('calls checkConsent on mount', async () => {
      const mockCheckConsent = vi.fn().mockResolvedValue(undefined)
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        checkConsent: mockCheckConsent,
      })

      renderAppLayout()

      await waitFor(() => {
        expect(mockCheckConsent).toHaveBeenCalledTimes(1)
      })
    })

    it('shows loading state while checking consent', () => {
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: null,
        isLoading: true,
      })

      renderAppLayout()

      expect(screen.getByText(/loading/i)).toBeInTheDocument()
    })
  })

  describe('consent dialog display', () => {
    it('shows consent dialog when needsConsent is true', () => {
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: true,
        isLoading: false,
      })

      renderAppLayout()

      expect(screen.getByTestId('consent-dialog')).toBeInTheDocument()
      // Child content should NOT be rendered - prevents API calls that cause infinite 451 loops
      expect(screen.queryByTestId('child-content')).not.toBeInTheDocument()
    })

    it('does not show consent dialog when needsConsent is false', () => {
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: false,
        isLoading: false,
      })

      renderAppLayout()

      expect(screen.queryByTestId('consent-dialog')).not.toBeInTheDocument()
      expect(screen.getByTestId('child-content')).toBeInTheDocument()
    })

    it('does not show consent dialog while still checking (needsConsent is null)', () => {
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: null,
        isLoading: true,
      })

      renderAppLayout()

      expect(screen.queryByTestId('consent-dialog')).not.toBeInTheDocument()
    })
  })

  describe('dev mode bypass', () => {
    it('skips consent check entirely in dev mode', async () => {
      vi.mocked(config).isDevMode = true
      const mockCheckConsent = vi.fn().mockResolvedValue(undefined)
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        checkConsent: mockCheckConsent,
      })

      renderAppLayout()

      // Wait a tick to ensure useEffect has run
      await waitFor(() => {
        expect(mockCheckConsent).not.toHaveBeenCalled()
      })
    })

    it('renders child content immediately in dev mode', () => {
      vi.mocked(config).isDevMode = true
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: null, // Not checked
      })

      renderAppLayout()

      expect(screen.getByTestId('child-content')).toBeInTheDocument()
      expect(screen.queryByTestId('consent-dialog')).not.toBeInTheDocument()
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument()
    })

    it('never shows consent dialog in dev mode even if needsConsent is true', () => {
      vi.mocked(config).isDevMode = true
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: true, // Would normally show dialog
      })

      renderAppLayout()

      expect(screen.queryByTestId('consent-dialog')).not.toBeInTheDocument()
      expect(screen.getByTestId('child-content')).toBeInTheDocument()
    })
  })

  describe('child content rendering', () => {
    it('renders Outlet for child routes', () => {
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: false,
      })

      renderAppLayout()

      expect(screen.getByTestId('child-content')).toBeInTheDocument()
    })
  })

  describe('consent flow completion', () => {
    it('hides dialog when consent is recorded (needsConsent becomes false)', () => {
      // Start with needsConsent true
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: true,
      })

      const { rerender } = renderAppLayout()
      expect(screen.getByTestId('consent-dialog')).toBeInTheDocument()

      // Simulate consent being recorded (needsConsent becomes false)
      mockUseConsentStore.mockReturnValue({
        ...defaultMockState,
        needsConsent: false,
      })

      rerender(
        <MemoryRouter initialEntries={['/app']}>
          <Routes>
            <Route path="/app" element={<AppLayout />}>
              <Route index element={<div data-testid="child-content">App Content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      )

      expect(screen.queryByTestId('consent-dialog')).not.toBeInTheDocument()
      expect(screen.getByTestId('child-content')).toBeInTheDocument()
    })
  })
})
