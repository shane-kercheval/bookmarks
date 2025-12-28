/**
 * Tests for useNotesQuery hook.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useNotesQuery, noteKeys } from './useNotesQuery'
import { api } from '../services/api'

vi.mock('../services/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

const mockGet = api.get as Mock

function createWrapper(): ({ children }: { children: ReactNode }) => ReactNode {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return function Wrapper({ children }: { children: ReactNode }): ReactNode {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

describe('useNotesQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('query execution', () => {
    it('should fetch notes with default params', async () => {
      const mockData = {
        items: [{ id: 1, title: 'Test Note', description: null, tags: [], version: 1 }],
        total: 1,
        offset: 0,
        limit: 20,
        has_more: false,
      }
      mockGet.mockResolvedValueOnce({ data: mockData })

      const { result } = renderHook(() => useNotesQuery({}), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockData)
      expect(mockGet).toHaveBeenCalledWith('/notes/')
    })

    it('should build query string from params', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } })

      const { result } = renderHook(
        () =>
          useNotesQuery({
            q: 'test',
            tags: ['react', 'typescript'],
            tag_match: 'all',
            sort_by: 'created_at',
            sort_order: 'desc',
            offset: 10,
            limit: 20,
            view: 'active',
          }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      const calledUrl = mockGet.mock.calls[0][0] as string
      expect(calledUrl).toContain('q=test')
      expect(calledUrl).toContain('tags=react')
      expect(calledUrl).toContain('tags=typescript')
      expect(calledUrl).toContain('tag_match=all')
      expect(calledUrl).toContain('sort_by=created_at')
      expect(calledUrl).toContain('sort_order=desc')
      expect(calledUrl).toContain('offset=10')
      expect(calledUrl).toContain('limit=20')
      expect(calledUrl).toContain('view=active')
    })

    it('should include list_id in query string', async () => {
      mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } })

      const { result } = renderHook(
        () =>
          useNotesQuery({
            view: 'active',
            list_id: 123,
          }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      const calledUrl = mockGet.mock.calls[0][0] as string
      expect(calledUrl).toContain('list_id=123')
    })

    it('should handle errors', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useNotesQuery({}), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toBeInstanceOf(Error)
    })

    it('should not fetch when enabled is false', async () => {
      const { result } = renderHook(
        () => useNotesQuery({}, { enabled: false }),
        { wrapper: createWrapper() }
      )

      // Should remain in initial loading state (pending)
      expect(result.current.isPending).toBe(true)
      expect(mockGet).not.toHaveBeenCalled()
    })
  })
})

describe('noteKeys', () => {
  describe('base keys', () => {
    it('should generate correct all key', () => {
      expect(noteKeys.all).toEqual(['notes'])
    })

    it('should generate correct lists prefix key', () => {
      expect(noteKeys.lists()).toEqual(['notes', 'list'])
    })
  })

  describe('view keys for invalidation', () => {
    it('should generate correct active view key', () => {
      expect(noteKeys.view('active')).toEqual(['notes', 'list', 'active'])
    })

    it('should generate correct archived view key', () => {
      expect(noteKeys.view('archived')).toEqual(['notes', 'list', 'archived'])
    })

    it('should generate correct deleted view key', () => {
      expect(noteKeys.view('deleted')).toEqual(['notes', 'list', 'deleted'])
    })

    it('should generate correct custom lists key', () => {
      expect(noteKeys.customLists()).toEqual(['notes', 'list', 'custom'])
    })
  })

  describe('list query keys', () => {
    it('should include view segment before params for active view', () => {
      const params = { view: 'active' as const, q: 'test' }
      const key = noteKeys.list(params)

      // Key should be ['notes', 'list', 'active', params]
      expect(key[0]).toBe('notes')
      expect(key[1]).toBe('list')
      expect(key[2]).toBe('active')
      expect(key[3]).toEqual(params)
    })

    it('should include view segment before params for archived view', () => {
      const params = { view: 'archived' as const }
      const key = noteKeys.list(params)

      expect(key).toEqual(['notes', 'list', 'archived', params])
    })

    it('should include view segment before params for deleted view', () => {
      const params = { view: 'deleted' as const }
      const key = noteKeys.list(params)

      expect(key).toEqual(['notes', 'list', 'deleted', params])
    })

    it('should default to active view when view is undefined', () => {
      const params = { q: 'test' }
      const key = noteKeys.list(params)

      expect(key[2]).toBe('active')
    })

    it('should use custom segment for queries with list_id', () => {
      const params = { view: 'active' as const, list_id: 123 }
      const key = noteKeys.list(params)

      // Custom lists use 'custom' segment instead of view
      expect(key).toEqual(['notes', 'list', 'custom', params])
    })
  })

  describe('prefix matching for invalidation', () => {
    it('view key should be prefix of list key for same view', () => {
      const viewKey = noteKeys.view('active')
      const listKey = noteKeys.list({ view: 'active', q: 'test' })

      // viewKey should be a prefix of listKey
      expect(listKey.slice(0, viewKey.length)).toEqual(viewKey)
    })

    it('customLists key should be prefix of list key with list_id', () => {
      const customKey = noteKeys.customLists()
      const listKey = noteKeys.list({ view: 'active', list_id: 123 })

      // customKey should be a prefix of listKey
      expect(listKey.slice(0, customKey.length)).toEqual(customKey)
    })

    it('active view key should NOT match archived list key', () => {
      const activeViewKey = noteKeys.view('active')
      const archivedListKey = noteKeys.list({ view: 'archived' })

      // These should be different at position 2
      expect(activeViewKey[2]).not.toBe(archivedListKey[2])
    })
  })
})
