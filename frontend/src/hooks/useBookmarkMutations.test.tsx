/**
 * Tests for useBookmarkMutations hooks.
 *
 * Tests both API calls AND cache invalidation behavior.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  useCreateBookmark,
  useUpdateBookmark,
  useDeleteBookmark,
  useRestoreBookmark,
  useArchiveBookmark,
  useUnarchiveBookmark,
} from './useBookmarkMutations'
import { bookmarkKeys } from './useBookmarksQuery'
import { contentKeys } from './useContentQuery'
import { api } from '../services/api'

vi.mock('../services/api', () => ({
  api: {
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockFetchTags = vi.fn()
vi.mock('../stores/tagsStore', () => ({
  useTagsStore: (selector: (state: { fetchTags: () => void }) => unknown) => {
    return selector({ fetchTags: mockFetchTags })
  },
}))

const mockPost = api.post as Mock
const mockPatch = api.patch as Mock
const mockDelete = api.delete as Mock

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

function createWrapper(queryClient: QueryClient): ({ children }: { children: ReactNode }) => ReactNode {
  return function Wrapper({ children }: { children: ReactNode }): ReactNode {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

describe('useCreateBookmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should create a bookmark', async () => {
    const queryClient = createTestQueryClient()
    const mockBookmark = {
      id: 1,
      url: 'https://example.com',
      title: 'Example',
      tags: ['test'],
    }
    mockPost.mockResolvedValueOnce({ data: mockBookmark })

    const { result } = renderHook(() => useCreateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    let created: unknown
    await act(async () => {
      created = await result.current.mutateAsync({
        url: 'https://example.com',
        title: 'Example',
        tags: ['test'],
      })
    })

    expect(created).toEqual(mockBookmark)
    expect(mockPost).toHaveBeenCalledWith('/bookmarks/', {
      url: 'https://example.com',
      title: 'Example',
      tags: ['test'],
    })
  })

  it('should invalidate active view and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useCreateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ url: 'https://example.com' })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    // Should NOT invalidate archived or deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useCreateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ url: 'https://example.com' })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })

  it('should throw on error', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockRejectedValueOnce(new Error('Duplicate URL'))

    const { result } = renderHook(() => useCreateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await expect(
      result.current.mutateAsync({ url: 'https://example.com' })
    ).rejects.toThrow('Duplicate URL')
  })
})

describe('useUpdateBookmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should update a bookmark', async () => {
    const queryClient = createTestQueryClient()
    const mockBookmark = {
      id: 1,
      url: 'https://example.com',
      title: 'Updated Title',
      tags: [],
    }
    mockPatch.mockResolvedValueOnce({ data: mockBookmark })

    const { result } = renderHook(() => useUpdateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    let updated: unknown
    await act(async () => {
      updated = await result.current.mutateAsync({
        id: 1,
        data: { title: 'Updated Title' },
      })
    })

    expect(updated).toEqual(mockBookmark)
    expect(mockPatch).toHaveBeenCalledWith('/bookmarks/1', { title: 'Updated Title' })
  })

  it('should invalidate active, archived, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPatch.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUpdateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, data: { title: 'New' } })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    // Should NOT invalidate deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPatch.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUpdateBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, data: { title: 'New' } })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useDeleteBookmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should soft delete a bookmark by default', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1 })
    })

    expect(mockDelete).toHaveBeenCalledWith('/bookmarks/1')
  })

  it('should invalidate active, deleted, and custom lists on soft delete', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1 })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
    // Should NOT invalidate archived
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
  })

  it('should permanently delete a bookmark when permanent=true', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, permanent: true })
    })

    expect(mockDelete).toHaveBeenCalledWith('/bookmarks/1?permanent=true')
  })

  it('should only invalidate deleted view on permanent delete', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, permanent: true })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
    // Should NOT invalidate active, archived, or custom lists
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
  })

  it('should refresh tags on soft delete', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1 })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })

  it('should refresh tags on permanent delete', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, permanent: true })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useRestoreBookmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should restore a deleted bookmark', async () => {
    const queryClient = createTestQueryClient()
    const mockBookmark = {
      id: 1,
      url: 'https://example.com',
      title: 'Example',
      deleted_at: null,
    }
    mockPost.mockResolvedValueOnce({ data: mockBookmark })

    const { result } = renderHook(() => useRestoreBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    let restored: unknown
    await act(async () => {
      restored = await result.current.mutateAsync(1)
    })

    expect(restored).toEqual(mockBookmark)
    expect(mockPost).toHaveBeenCalledWith('/bookmarks/1/restore')
  })

  it('should invalidate active, deleted, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useRestoreBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
    // Should NOT invalidate archived
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useRestoreBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useArchiveBookmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should archive a bookmark', async () => {
    const queryClient = createTestQueryClient()
    const mockBookmark = {
      id: 1,
      url: 'https://example.com',
      title: 'Example',
      archived_at: '2025-01-01T00:00:00Z',
    }
    mockPost.mockResolvedValueOnce({ data: mockBookmark })

    const { result } = renderHook(() => useArchiveBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    let archived: unknown
    await act(async () => {
      archived = await result.current.mutateAsync(1)
    })

    expect(archived).toEqual(mockBookmark)
    expect(mockPost).toHaveBeenCalledWith('/bookmarks/1/archive')
  })

  it('should invalidate active, archived, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useArchiveBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    // Should NOT invalidate deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useArchiveBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useUnarchiveBookmark', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should unarchive a bookmark', async () => {
    const queryClient = createTestQueryClient()
    const mockBookmark = {
      id: 1,
      url: 'https://example.com',
      title: 'Example',
      archived_at: null,
    }
    mockPost.mockResolvedValueOnce({ data: mockBookmark })

    const { result } = renderHook(() => useUnarchiveBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    let unarchived: unknown
    await act(async () => {
      unarchived = await result.current.mutateAsync(1)
    })

    expect(unarchived).toEqual(mockBookmark)
    expect(mockPost).toHaveBeenCalledWith('/bookmarks/1/unarchive')
  })

  it('should invalidate active, archived, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUnarchiveBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: bookmarkKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    // Should NOT invalidate deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: bookmarkKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUnarchiveBookmark(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})
