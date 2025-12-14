import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

// Mock all modules that make network requests or have complex dependencies
vi.mock('./hooks/useBookmarks', () => ({
  useBookmarks: () => ({
    bookmarks: [],
    total: 0,
    isLoading: false,
    error: null,
    fetchBookmarks: vi.fn(),
    createBookmark: vi.fn(),
    updateBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
    fetchMetadata: vi.fn(),
    clearError: vi.fn(),
  }),
}))

vi.mock('./hooks/useTags', () => ({
  useTags: () => ({
    tags: [],
    isLoading: false,
    error: null,
    fetchTags: vi.fn(),
    clearError: vi.fn(),
  }),
}))

// Mock the config module to control isDevMode
vi.mock('./config', () => ({
  config: {
    apiUrl: 'http://localhost:8000',
    auth0: {
      domain: '',
      clientId: '',
      audience: '',
    },
  },
  isDevMode: true,
}))

// Must import App AFTER mocks are set up
import App from './App'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render and redirect to bookmarks page in dev mode', async () => {
    render(<App />)

    // In dev mode, the landing page redirects to bookmarks
    // Wait for the redirect and bookmarks content to appear
    await waitFor(
      () => {
        expect(screen.getByText('Your Bookmarks')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })

  it('should show dev mode banner in dev mode', async () => {
    render(<App />)

    await waitFor(
      () => {
        expect(screen.getByText(/Dev Mode/i)).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })

  it('should show Bookmarks header link in dev mode', async () => {
    render(<App />)

    await waitFor(
      () => {
        expect(screen.getByRole('link', { name: 'Bookmarks' })).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })

  it('should show Add Bookmark button in header', async () => {
    render(<App />)

    await waitFor(
      () => {
        // There are two "Add Bookmark" buttons - one in header and one in empty state
        const buttons = screen.getAllByText('Add Bookmark')
        expect(buttons.length).toBeGreaterThanOrEqual(1)
      },
      { timeout: 3000 }
    )
  })

  it('should show empty state when no bookmarks exist', async () => {
    render(<App />)

    await waitFor(
      () => {
        expect(screen.getByText('No bookmarks yet')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )
  })
})
