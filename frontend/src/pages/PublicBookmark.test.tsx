/**
 * Public bookmark page: bookmarks are deliberately excluded from the ToC
 * (scraped content is formatting-stripped and headingless — see the
 * editor-improvements plan), so the shell must close a stale ToC panel on
 * mount and render no sidebar.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { PublicBookmark } from './PublicBookmark'
import { useRightSidebarStore } from '../stores/rightSidebarStore'
import type { PublicBookmark as PublicBookmarkType } from '../types'

let mockBookmarkQuery: Partial<UseQueryResult<PublicBookmarkType>>
vi.mock('../hooks/usePublicItem', () => ({
  usePublicBookmark: () => mockBookmarkQuery,
}))

// Stub the heavy editors.
vi.mock('../components/CodeMirrorEditor', () => ({
  CodeMirrorEditor: ({ value }: { value: string }) => (
    <textarea data-testid="content-editor" value={value} onChange={() => {}} />
  ),
}))
vi.mock('../components/MilkdownEditor', () => ({
  MilkdownEditor: ({ value }: { value: string }) => <div>{value}</div>,
}))

const activeBookmark: PublicBookmarkType = {
  url: 'https://example.com',
  title: 'My Bookmark',
  description: 'A description',
  content: 'Scraped body',
  is_archived: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/shared/bookmarks/tok']}>
        <Routes>
          <Route path="/shared/bookmarks/:token" element={<PublicBookmark />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('PublicBookmark page — no ToC support', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useRightSidebarStore.setState({ activePanel: null, maximized: false })
    mockBookmarkQuery = { data: activeBookmark, isLoading: false, isError: false }
  })

  it('closes a stale ToC panel on mount and renders no sidebar or offset', () => {
    useRightSidebarStore.setState({ activePanel: 'toc' })
    renderPage()

    expect(screen.getByText('My Bookmark')).toBeInTheDocument()
    expect(useRightSidebarStore.getState().activePanel).toBeNull()
    expect(screen.queryByText('Table of Contents')).toBeNull()
    expect(document.querySelector('[style*="margin-right"]')).toBeNull()
  })
})
