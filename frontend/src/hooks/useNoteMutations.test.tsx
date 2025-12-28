/**
 * Tests for useNoteMutations hooks.
 *
 * Tests both API calls AND cache invalidation behavior.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  useCreateNote,
  useUpdateNote,
  useDeleteNote,
  useRestoreNote,
  useArchiveNote,
  useUnarchiveNote,
} from './useNoteMutations'
import { noteKeys } from './useNotesQuery'
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

describe('useCreateNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should create a note', async () => {
    const queryClient = createTestQueryClient()
    const mockNote = {
      id: 1,
      title: 'Test Note',
      description: 'A test note',
      content: '# Hello World',
      tags: ['test'],
      version: 1,
    }
    mockPost.mockResolvedValueOnce({ data: mockNote })

    const { result } = renderHook(() => useCreateNote(), {
      wrapper: createWrapper(queryClient),
    })

    let created: unknown
    await act(async () => {
      created = await result.current.mutateAsync({
        title: 'Test Note',
        description: 'A test note',
        content: '# Hello World',
        tags: ['test'],
      })
    })

    expect(created).toEqual(mockNote)
    expect(mockPost).toHaveBeenCalledWith('/notes/', {
      title: 'Test Note',
      description: 'A test note',
      content: '# Hello World',
      tags: ['test'],
    })
  })

  it('should invalidate active view and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useCreateNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ title: 'Test Note' })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    // Should NOT invalidate archived or deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useCreateNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ title: 'Test Note' })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })

  it('should throw on error', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockRejectedValueOnce(new Error('Validation error'))

    const { result } = renderHook(() => useCreateNote(), {
      wrapper: createWrapper(queryClient),
    })

    await expect(
      result.current.mutateAsync({ title: 'Test Note' })
    ).rejects.toThrow('Validation error')
  })
})

describe('useUpdateNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should update a note', async () => {
    const queryClient = createTestQueryClient()
    const mockNote = {
      id: 1,
      title: 'Updated Title',
      description: null,
      content: '# Updated',
      tags: [],
      version: 2,
    }
    mockPatch.mockResolvedValueOnce({ data: mockNote })

    const { result } = renderHook(() => useUpdateNote(), {
      wrapper: createWrapper(queryClient),
    })

    let updated: unknown
    await act(async () => {
      updated = await result.current.mutateAsync({
        id: 1,
        data: { title: 'Updated Title' },
      })
    })

    expect(updated).toEqual(mockNote)
    expect(mockPatch).toHaveBeenCalledWith('/notes/1', { title: 'Updated Title' })
  })

  it('should invalidate active, archived, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPatch.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUpdateNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, data: { title: 'New' } })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    // Should NOT invalidate deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPatch.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUpdateNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, data: { title: 'New' } })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useDeleteNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should soft delete a note by default', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1 })
    })

    expect(mockDelete).toHaveBeenCalledWith('/notes/1')
  })

  it('should invalidate active, archived, deleted, and custom lists on soft delete', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1 })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should permanently delete a note when permanent=true', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, permanent: true })
    })

    expect(mockDelete).toHaveBeenCalledWith('/notes/1?permanent=true')
  })

  it('should only invalidate deleted view on permanent delete', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, permanent: true })
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
    // Should NOT invalidate active, archived, or custom lists
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
  })

  it('should refresh tags on soft delete', async () => {
    const queryClient = createTestQueryClient()
    mockDelete.mockResolvedValueOnce({})

    const { result } = renderHook(() => useDeleteNote(), {
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

    const { result } = renderHook(() => useDeleteNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ id: 1, permanent: true })
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useRestoreNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should restore a deleted note', async () => {
    const queryClient = createTestQueryClient()
    const mockNote = {
      id: 1,
      title: 'Test Note',
      deleted_at: null,
      version: 1,
    }
    mockPost.mockResolvedValueOnce({ data: mockNote })

    const { result } = renderHook(() => useRestoreNote(), {
      wrapper: createWrapper(queryClient),
    })

    let restored: unknown
    await act(async () => {
      restored = await result.current.mutateAsync(1)
    })

    expect(restored).toEqual(mockNote)
    expect(mockPost).toHaveBeenCalledWith('/notes/1/restore')
  })

  it('should invalidate active, deleted, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useRestoreNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
    // Should NOT invalidate archived
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useRestoreNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useArchiveNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should archive a note', async () => {
    const queryClient = createTestQueryClient()
    const mockNote = {
      id: 1,
      title: 'Test Note',
      archived_at: '2025-01-01T00:00:00Z',
      version: 1,
    }
    mockPost.mockResolvedValueOnce({ data: mockNote })

    const { result } = renderHook(() => useArchiveNote(), {
      wrapper: createWrapper(queryClient),
    })

    let archived: unknown
    await act(async () => {
      archived = await result.current.mutateAsync(1)
    })

    expect(archived).toEqual(mockNote)
    expect(mockPost).toHaveBeenCalledWith('/notes/1/archive')
  })

  it('should invalidate active, archived, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useArchiveNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    // Should NOT invalidate deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useArchiveNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})

describe('useUnarchiveNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should unarchive a note', async () => {
    const queryClient = createTestQueryClient()
    const mockNote = {
      id: 1,
      title: 'Test Note',
      archived_at: null,
      version: 1,
    }
    mockPost.mockResolvedValueOnce({ data: mockNote })

    const { result } = renderHook(() => useUnarchiveNote(), {
      wrapper: createWrapper(queryClient),
    })

    let unarchived: unknown
    await act(async () => {
      unarchived = await result.current.mutateAsync(1)
    })

    expect(unarchived).toEqual(mockNote)
    expect(mockPost).toHaveBeenCalledWith('/notes/1/unarchive')
  })

  it('should invalidate active, archived, and custom lists on success', async () => {
    const queryClient = createTestQueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUnarchiveNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.view('archived') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: noteKeys.customLists() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('active') })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: contentKeys.view('archived') })
    // Should NOT invalidate deleted
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: noteKeys.view('deleted') })
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: contentKeys.view('deleted') })
  })

  it('should refresh tags on success', async () => {
    const queryClient = createTestQueryClient()
    mockPost.mockResolvedValueOnce({ data: { id: 1 } })

    const { result } = renderHook(() => useUnarchiveNote(), {
      wrapper: createWrapper(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync(1)
    })

    expect(mockFetchTags).toHaveBeenCalled()
  })
})
