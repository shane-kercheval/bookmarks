import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useBookmarks } from './useBookmarks'
import { api } from '../services/api'

vi.mock('../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockGet = api.get as Mock
const mockPost = api.post as Mock
const mockPatch = api.patch as Mock
const mockDelete = api.delete as Mock

describe('useBookmarks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should have empty bookmarks and not loading initially', () => {
      const { result } = renderHook(() => useBookmarks())

      expect(result.current.bookmarks).toEqual([])
      expect(result.current.total).toBe(0)
      expect(result.current.isLoading).toBe(false)
      expect(result.current.error).toBeNull()
    })
  })

  describe('fetchBookmarks', () => {
    it('should fetch bookmarks and update state', async () => {
      const mockBookmarks = [
        { id: 1, url: 'https://example.com', title: 'Example', tags: [] },
        { id: 2, url: 'https://test.com', title: 'Test', tags: [] },
      ]
      mockGet.mockResolvedValueOnce({
        data: { items: mockBookmarks, total: 2 },
      })

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.fetchBookmarks()
      })

      expect(result.current.bookmarks).toEqual(mockBookmarks)
      expect(result.current.total).toBe(2)
      expect(result.current.isLoading).toBe(false)
      expect(result.current.error).toBeNull()
      expect(mockGet).toHaveBeenCalledWith('/bookmarks/', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    })

    it('should build query string with search params', async () => {
      mockGet.mockResolvedValueOnce({
        data: { items: [], total: 0 },
      })

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.fetchBookmarks({
          q: 'test',
          tags: ['react', 'typescript'],
          sort_by: 'created_at',
          sort_order: 'desc',
        })
      })

      const calledUrl = mockGet.mock.calls[0][0] as string
      expect(calledUrl).toContain('q=test')
      expect(calledUrl).toContain('tags=react')
      expect(calledUrl).toContain('tags=typescript')
      expect(calledUrl).toContain('sort_by=created_at')
      expect(calledUrl).toContain('sort_order=desc')
    })

    it('should include view parameter in query string', async () => {
      mockGet.mockResolvedValueOnce({
        data: { items: [], total: 0 },
      })

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.fetchBookmarks({
          view: 'archived',
        })
      })

      const calledUrl = mockGet.mock.calls[0][0] as string
      expect(calledUrl).toContain('view=archived')
    })

    it('should include view=deleted parameter for trash view', async () => {
      mockGet.mockResolvedValueOnce({
        data: { items: [], total: 0 },
      })

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.fetchBookmarks({
          view: 'deleted',
        })
      })

      const calledUrl = mockGet.mock.calls[0][0] as string
      expect(calledUrl).toContain('view=deleted')
    })

    it('should set error on fetch failure', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.fetchBookmarks()
      })

      expect(result.current.bookmarks).toEqual([])
      expect(result.current.error).toBe('Network error')
      expect(result.current.isLoading).toBe(false)
    })

    it('should set isLoading during fetch', async () => {
      let resolvePromise: (value: unknown) => void
      mockGet.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve
          })
      )

      const { result } = renderHook(() => useBookmarks())

      act(() => {
        result.current.fetchBookmarks()
      })

      await waitFor(() => {
        expect(result.current.isLoading).toBe(true)
      })

      await act(async () => {
        resolvePromise!({ data: { items: [], total: 0 } })
      })

      expect(result.current.isLoading).toBe(false)
    })
  })

  describe('createBookmark', () => {
    it('should create a bookmark and return it', async () => {
      const newBookmark = {
        id: 1,
        url: 'https://example.com',
        title: 'Example',
        tags: ['test'],
      }
      mockPost.mockResolvedValueOnce({ data: newBookmark })

      const { result } = renderHook(() => useBookmarks())

      let created: unknown
      await act(async () => {
        created = await result.current.createBookmark({
          url: 'https://example.com',
          title: 'Example',
          tags: ['test'],
        })
      })

      expect(created).toEqual(newBookmark)
      expect(mockPost).toHaveBeenCalledWith('/bookmarks/', {
        url: 'https://example.com',
        title: 'Example',
        tags: ['test'],
      })
    })
  })

  describe('updateBookmark', () => {
    it('should update a bookmark and return it', async () => {
      const updatedBookmark = {
        id: 1,
        url: 'https://example.com',
        title: 'Updated Title',
        tags: [],
      }
      mockPatch.mockResolvedValueOnce({ data: updatedBookmark })

      const { result } = renderHook(() => useBookmarks())

      let updated: unknown
      await act(async () => {
        updated = await result.current.updateBookmark(1, {
          title: 'Updated Title',
        })
      })

      expect(updated).toEqual(updatedBookmark)
      expect(mockPatch).toHaveBeenCalledWith('/bookmarks/1', {
        title: 'Updated Title',
      })
    })
  })

  describe('deleteBookmark', () => {
    it('should soft delete a bookmark by default', async () => {
      mockDelete.mockResolvedValueOnce({})

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.deleteBookmark(1)
      })

      expect(mockDelete).toHaveBeenCalledWith('/bookmarks/1')
    })

    it('should permanently delete a bookmark when permanent=true', async () => {
      mockDelete.mockResolvedValueOnce({})

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.deleteBookmark(1, true)
      })

      expect(mockDelete).toHaveBeenCalledWith('/bookmarks/1?permanent=true')
    })
  })

  describe('restoreBookmark', () => {
    it('should restore a bookmark and return it', async () => {
      const restoredBookmark = {
        id: 1,
        url: 'https://example.com',
        title: 'Example',
        tags: [],
        deleted_at: null,
        archived_at: null,
      }
      mockPost.mockResolvedValueOnce({ data: restoredBookmark })

      const { result } = renderHook(() => useBookmarks())

      let restored: unknown
      await act(async () => {
        restored = await result.current.restoreBookmark(1)
      })

      expect(restored).toEqual(restoredBookmark)
      expect(mockPost).toHaveBeenCalledWith('/bookmarks/1/restore')
    })
  })

  describe('archiveBookmark', () => {
    it('should archive a bookmark and return it', async () => {
      const archivedBookmark = {
        id: 1,
        url: 'https://example.com',
        title: 'Example',
        tags: [],
        deleted_at: null,
        archived_at: '2025-01-01T00:00:00Z',
      }
      mockPost.mockResolvedValueOnce({ data: archivedBookmark })

      const { result } = renderHook(() => useBookmarks())

      let archived: unknown
      await act(async () => {
        archived = await result.current.archiveBookmark(1)
      })

      expect(archived).toEqual(archivedBookmark)
      expect(mockPost).toHaveBeenCalledWith('/bookmarks/1/archive')
    })
  })

  describe('unarchiveBookmark', () => {
    it('should unarchive a bookmark and return it', async () => {
      const unarchivedBookmark = {
        id: 1,
        url: 'https://example.com',
        title: 'Example',
        tags: [],
        deleted_at: null,
        archived_at: null,
      }
      mockPost.mockResolvedValueOnce({ data: unarchivedBookmark })

      const { result } = renderHook(() => useBookmarks())

      let unarchived: unknown
      await act(async () => {
        unarchived = await result.current.unarchiveBookmark(1)
      })

      expect(unarchived).toEqual(unarchivedBookmark)
      expect(mockPost).toHaveBeenCalledWith('/bookmarks/1/unarchive')
    })
  })

  describe('fetchMetadata', () => {
    it('should fetch metadata for a URL', async () => {
      const mockMetadata = {
        title: 'Example Site',
        description: 'A sample site',
        image_url: 'https://example.com/image.png',
      }
      mockGet.mockResolvedValueOnce({ data: mockMetadata })

      const { result } = renderHook(() => useBookmarks())

      let metadata: unknown
      await act(async () => {
        metadata = await result.current.fetchMetadata('https://example.com')
      })

      expect(metadata).toEqual(mockMetadata)
      expect(mockGet).toHaveBeenCalledWith('/bookmarks/fetch-metadata', {
        params: { url: 'https://example.com', include_content: true },
      })
    })
  })

  describe('clearError', () => {
    it('should clear the error state', async () => {
      mockGet.mockRejectedValueOnce(new Error('Test error'))

      const { result } = renderHook(() => useBookmarks())

      await act(async () => {
        await result.current.fetchBookmarks()
      })

      expect(result.current.error).toBe('Test error')

      act(() => {
        result.current.clearError()
      })

      expect(result.current.error).toBeNull()
    })
  })
})
