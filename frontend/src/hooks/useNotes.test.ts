/**
 * Tests for useNotes hook (non-cacheable utilities).
 *
 * For query tests, see useNotesQuery.test.tsx.
 * For mutation tests, see useNoteMutations.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useNotes } from './useNotes'
import { api } from '../services/api'

vi.mock('../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

const mockGet = api.get as Mock
const mockPost = api.post as Mock

describe('useNotes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('fetchNote', () => {
    it('should fetch a single note by ID', async () => {
      const mockNote = {
        id: 1,
        title: 'Test Note',
        description: 'A test note',
        content: '# Hello World\n\nThis is the note content.',
        tags: ['test', 'example'],
        version: 1,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
        last_used_at: '2025-01-01T00:00:00Z',
        deleted_at: null,
        archived_at: null,
      }
      mockGet.mockResolvedValueOnce({ data: mockNote })

      const { result } = renderHook(() => useNotes())

      let fetched: unknown
      await act(async () => {
        fetched = await result.current.fetchNote(1)
      })

      expect(fetched).toEqual(mockNote)
      expect(mockGet).toHaveBeenCalledWith('/notes/1')
    })

    it('should throw error on fetch failure', async () => {
      mockGet.mockRejectedValueOnce(new Error('Not found'))

      const { result } = renderHook(() => useNotes())

      await expect(result.current.fetchNote(999)).rejects.toThrow('Not found')
    })
  })

  describe('trackNoteUsage', () => {
    it('should call track-usage endpoint (fire-and-forget)', async () => {
      mockPost.mockResolvedValueOnce({})

      const { result } = renderHook(() => useNotes())

      act(() => {
        result.current.trackNoteUsage(1)
      })

      expect(mockPost).toHaveBeenCalledWith('/notes/1/track-usage')
    })

    it('should silently ignore errors', async () => {
      mockPost.mockRejectedValueOnce(new Error('Server error'))

      const { result } = renderHook(() => useNotes())

      // Should not throw
      act(() => {
        result.current.trackNoteUsage(1)
      })

      expect(mockPost).toHaveBeenCalledWith('/notes/1/track-usage')
    })
  })
})
