/**
 * TanStack Query mutation hooks for note operations.
 *
 * Each mutation hook handles:
 * - API call
 * - Granular cache invalidation based on which views are affected
 * - Tag store refresh when tags might change
 *
 * Cache Invalidation Strategy:
 * | Mutation          | Invalidates                                    |
 * |-------------------|------------------------------------------------|
 * | Create note       | active, custom lists                           |
 * | Update note       | active, archived, custom lists                 |
 * | Delete (soft)     | active, archived, deleted, custom lists        |
 * | Delete (permanent)| deleted only                                   |
 * | Archive           | active, archived, custom lists                 |
 * | Unarchive         | active, archived, custom lists                 |
 * | Restore           | active, deleted, custom lists                  |
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import { noteKeys } from './useNotesQuery'
import { contentKeys } from './useContentQuery'
import { useTagsStore } from '../stores/tagsStore'
import type { Note, NoteCreate, NoteUpdate } from '../types'

/**
 * Hook for creating a new note.
 *
 * New notes are always active, so invalidates:
 * - Active view queries
 * - Custom list queries (new note's tags may match list filters)
 */
export function useCreateNote() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (data: NoteCreate): Promise<Note> => {
      const response = await api.post<Note>('/notes/', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: noteKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: noteKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      fetchTags()
    },
  })
}

/**
 * Hook for updating an existing note.
 *
 * Updates can affect active or archived notes, so invalidates:
 * - Active view queries
 * - Archived view queries
 * - Custom list queries (tag changes may affect list membership)
 */
export function useUpdateNote() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: NoteUpdate }): Promise<Note> => {
      const response = await api.patch<Note>(`/notes/${id}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: noteKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: noteKeys.view('archived') })
      queryClient.invalidateQueries({ queryKey: noteKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
      fetchTags()
    },
  })
}

/**
 * Hook for deleting a note (soft or permanent).
 *
 * Soft delete: moves from active/archived to deleted
 * - Active view queries
 * - Archived view queries (note can be deleted from archive)
 * - Deleted view queries
 * - Custom list queries (note removed from lists)
 *
 * Permanent delete: removes from trash only
 * - Deleted view queries only
 */
export function useDeleteNote() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async ({ id, permanent = false }: { id: number; permanent?: boolean }): Promise<void> => {
      const url = permanent ? `/notes/${id}?permanent=true` : `/notes/${id}`
      await api.delete(url)
    },
    onSuccess: (_, { permanent }) => {
      if (permanent) {
        // Permanent delete only affects trash
        queryClient.invalidateQueries({ queryKey: noteKeys.view('deleted') })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('deleted') })
      } else {
        // Soft delete moves from active/archived to deleted
        queryClient.invalidateQueries({ queryKey: noteKeys.view('active') })
        queryClient.invalidateQueries({ queryKey: noteKeys.view('archived') })
        queryClient.invalidateQueries({ queryKey: noteKeys.view('deleted') })
        queryClient.invalidateQueries({ queryKey: noteKeys.customLists() })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('deleted') })
      }
      fetchTags()
    },
  })
}

/**
 * Hook for restoring a deleted note.
 *
 * Moves note from deleted back to active, so invalidates:
 * - Active view queries
 * - Deleted view queries
 * - Custom list queries (restored note may match list filters)
 */
export function useRestoreNote() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (id: number): Promise<Note> => {
      const response = await api.post<Note>(`/notes/${id}/restore`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: noteKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: noteKeys.view('deleted') })
      queryClient.invalidateQueries({ queryKey: noteKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('deleted') })
      fetchTags()
    },
  })
}

/**
 * Hook for archiving a note.
 *
 * Moves note from active to archived, so invalidates:
 * - Active view queries
 * - Archived view queries
 * - Custom list queries (note removed from active lists)
 */
export function useArchiveNote() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (id: number): Promise<Note> => {
      const response = await api.post<Note>(`/notes/${id}/archive`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: noteKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: noteKeys.view('archived') })
      queryClient.invalidateQueries({ queryKey: noteKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
      fetchTags()
    },
  })
}

/**
 * Hook for unarchiving a note.
 *
 * Moves note from archived back to active, so invalidates:
 * - Active view queries
 * - Archived view queries
 * - Custom list queries (note may now match list filters)
 */
export function useUnarchiveNote() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (id: number): Promise<Note> => {
      const response = await api.post<Note>(`/notes/${id}/unarchive`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: noteKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: noteKeys.view('archived') })
      queryClient.invalidateQueries({ queryKey: noteKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
      fetchTags()
    },
  })
}
