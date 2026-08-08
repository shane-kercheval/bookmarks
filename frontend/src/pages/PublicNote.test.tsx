/**
 * Integration tests for the public note read page (the thin wrapper + shared
 * shell + reused Note render component, end to end). Covers the public-view outcomes:
 * content renders read-only, the archived banner, the not-found state, the
 * loading state, and the auth-aware Save-a-copy control (authenticated via the
 * global useAuthStatus mock).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { PublicNote } from './PublicNote'
import { useRightSidebarStore } from '../stores/rightSidebarStore'
import type { PublicNote as PublicNoteType } from '../types'

// `mock`-prefixed so the hoisted factory may reference it.
let mockNoteQuery: Partial<UseQueryResult<PublicNoteType>>
vi.mock('../hooks/usePublicItem', () => ({
  usePublicNote: () => mockNoteQuery,
}))

// Stub the heavy editor.
vi.mock('../components/CodeMirrorEditor', () => ({
  CodeMirrorEditor: ({ value, onChange, disabled }: {
    value: string
    onChange: (v: string) => void
    disabled?: boolean
  }) => (
    <textarea data-testid="content-editor" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} />
  ),
}))
vi.mock('../components/MilkdownEditor', () => ({
  MilkdownEditor: ({ value }: { value: string }) => <div>{value}</div>,
}))

const activeNote: PublicNoteType = {
  title: 'My Note',
  description: 'A description',
  content: 'Body text',
  is_archived: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderPage(): { container: HTMLElement; unmount: () => void } {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { container, unmount } = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/shared/notes/tok']}>
        <Routes>
          <Route path="/shared/notes/:token" element={<PublicNote />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
  return { container, unmount }
}

describe('PublicNote page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the note read-only with a Save-a-copy action and no edit UI', () => {
    mockNoteQuery = { data: activeNote, isLoading: false, isError: false }
    renderPage()

    expect(screen.getByText('My Note')).toBeInTheDocument()
    expect(screen.getByTestId('content-editor')).toHaveValue('Body text')
    expect(screen.getByRole('button', { name: 'Save to Tiddly' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /close/i })).toBeNull()
    expect(screen.queryByText('Archived')).toBeNull()
  })

  it('shows the archived banner for an archived shared note', () => {
    mockNoteQuery = { data: { ...activeNote, is_archived: true }, isLoading: false, isError: false }
    renderPage()
    expect(screen.getByText('Archived')).toBeInTheDocument()
  })

  it('shows a loading state while fetching', () => {
    mockNoteQuery = { data: undefined, isLoading: true, isError: false }
    renderPage()
    expect(screen.getByText('Loading shared item...')).toBeInTheDocument()
  })

  it('shows a not-found state for an invalid/unpublished token (404)', () => {
    mockNoteQuery = {
      data: undefined,
      isLoading: false,
      isError: true,
      error: { isAxiosError: true, response: { status: 404 } } as unknown as Error,
    }
    renderPage()
    expect(screen.getByText(/isn’t available/i)).toBeInTheDocument()
    expect(screen.queryByTestId('content-editor')).toBeNull()
  })

  describe('ToC sidebar', () => {
    beforeEach(() => {
      useRightSidebarStore.setState({ activePanel: null, maximized: false })
      mockNoteQuery = { data: activeNote, isLoading: false, isError: false }
    })

    it('opening the ToC renders the sidebar', () => {
      // The content offset while the panel is open is owned by
      // PublicSharedTocLayout (tested in PublicPageLayout.test.tsx).
      useRightSidebarStore.setState({ activePanel: 'toc' })
      renderPage()

      expect(screen.getByText('Table of Contents')).toBeInTheDocument()
    })

    it('a persisted history panel renders no sidebar and is left alone', () => {
      // The store restores 'history' from a prior app session; no public page
      // can render that panel. Only 'toc' is shell-managed.
      useRightSidebarStore.setState({ activePanel: 'history' })
      renderPage()

      expect(screen.queryByText('Table of Contents')).toBeNull()
      expect(useRightSidebarStore.getState().activePanel).toBe('history')
    })

    it('navigating away closes the ToC (no orphaned panel on pricing/changelog)', () => {
      useRightSidebarStore.setState({ activePanel: 'toc' })
      const { unmount } = renderPage()
      expect(useRightSidebarStore.getState().activePanel).toBe('toc')

      unmount()
      expect(useRightSidebarStore.getState().activePanel).toBeNull()
    })
  })
})
