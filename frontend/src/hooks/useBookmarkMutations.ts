/**
 * TanStack Query mutation hooks for bookmark operations.
 *
 * Each mutation hook handles:
 * - API call
 * - Granular cache invalidation based on which views are affected
 * - Tag store refresh when tags might change
 *
 * Cache Invalidation Strategy:
 * | Mutation          | Invalidates                                    |
 * |-------------------|------------------------------------------------|
 * | Create bookmark   | active, custom lists                           |
 * | Update bookmark   | active, archived, custom lists                 |
 * | Delete (soft)     | active, deleted, custom lists                  |
 * | Delete (permanent)| deleted only                                   |
 * | Archive           | active, archived, custom lists                 |
 * | Unarchive         | active, archived, custom lists                 |
 * | Restore           | active, deleted, custom lists                  |
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import { bookmarkKeys } from './useBookmarksQuery'
import { contentKeys } from './useContentQuery'
import { useTagsStore } from '../stores/tagsStore'
import type { Bookmark, BookmarkCreate, BookmarkUpdate } from '../types'

/**
 * Hook for creating a new bookmark.
 *
 * New bookmarks are always active, so invalidates:
 * - Active view queries
 * - Custom list queries (new bookmark's tags may match list filters)
 */
export function useCreateBookmark() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (data: BookmarkCreate): Promise<Bookmark> => {
      const response = await api.post<Bookmark>('/bookmarks/', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      fetchTags()
    },
  })
}

/**
 * Hook for updating an existing bookmark.
 *
 * Updates can affect active or archived bookmarks, so invalidates:
 * - Active view queries
 * - Archived view queries
 * - Custom list queries (tag changes may affect list membership)
 */
export function useUpdateBookmark() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: BookmarkUpdate }): Promise<Bookmark> => {
      const response = await api.patch<Bookmark>(`/bookmarks/${id}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('archived') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
      fetchTags()
    },
  })
}

/**
 * Hook for deleting a bookmark (soft or permanent).
 *
 * Soft delete: moves from active to deleted
 * - Active view queries
 * - Deleted view queries
 * - Custom list queries (bookmark removed from lists)
 *
 * Permanent delete: removes from trash only
 * - Deleted view queries only
 */
export function useDeleteBookmark() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async ({ id, permanent = false }: { id: number; permanent?: boolean }): Promise<void> => {
      const url = permanent ? `/bookmarks/${id}?permanent=true` : `/bookmarks/${id}`
      await api.delete(url)
    },
    onSuccess: (_, { permanent }) => {
      if (permanent) {
        // Permanent delete only affects trash
        queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('deleted') })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('deleted') })
      } else {
        // Soft delete moves from active to deleted
        queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('active') })
        queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('deleted') })
        queryClient.invalidateQueries({ queryKey: bookmarkKeys.customLists() })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
        queryClient.invalidateQueries({ queryKey: contentKeys.view('deleted') })
      }
      fetchTags()
    },
  })
}

/**
 * Hook for restoring a deleted bookmark.
 *
 * Moves bookmark from deleted back to active, so invalidates:
 * - Active view queries
 * - Deleted view queries
 * - Custom list queries (restored bookmark may match list filters)
 */
export function useRestoreBookmark() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (id: number): Promise<Bookmark> => {
      const response = await api.post<Bookmark>(`/bookmarks/${id}/restore`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('deleted') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('deleted') })
      fetchTags()
    },
  })
}

/**
 * Hook for archiving a bookmark.
 *
 * Moves bookmark from active to archived, so invalidates:
 * - Active view queries
 * - Archived view queries
 * - Custom list queries (bookmark removed from active lists)
 */
export function useArchiveBookmark() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (id: number): Promise<Bookmark> => {
      const response = await api.post<Bookmark>(`/bookmarks/${id}/archive`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('archived') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
      fetchTags()
    },
  })
}

/**
 * Hook for unarchiving a bookmark.
 *
 * Moves bookmark from archived back to active, so invalidates:
 * - Active view queries
 * - Archived view queries
 * - Custom list queries (bookmark may now match list filters)
 */
export function useUnarchiveBookmark() {
  const queryClient = useQueryClient()
  const fetchTags = useTagsStore((state) => state.fetchTags)

  return useMutation({
    mutationFn: async (id: number): Promise<Bookmark> => {
      const response = await api.post<Bookmark>(`/bookmarks/${id}/unarchive`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.view('archived') })
      queryClient.invalidateQueries({ queryKey: bookmarkKeys.customLists() })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('active') })
      queryClient.invalidateQueries({ queryKey: contentKeys.view('archived') })
      fetchTags()
    },
  })
}
