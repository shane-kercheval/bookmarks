/**
 * Bookmarks page - main bookmark list view with search, filter, and CRUD operations.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useBookmarks } from '../hooks/useBookmarks'
import { useTags } from '../hooks/useTags'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
import { BookmarkCard } from '../components/BookmarkCard'
import { BookmarkModal } from '../components/BookmarkModal'
import { ShortcutsDialog } from '../components/ShortcutsDialog'
import type { Bookmark, BookmarkCreate, BookmarkUpdate, BookmarkSearchParams } from '../types'

/** Default pagination limit */
const DEFAULT_LIMIT = 50

/**
 * Loading spinner component.
 */
function LoadingSpinner(): ReactNode {
  return (
    <div className="flex justify-center py-12">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
    </div>
  )
}

/**
 * Empty state component.
 */
function EmptyState({
  hasFilters,
  onAddBookmark,
}: {
  hasFilters: boolean
  onAddBookmark: () => void
}): ReactNode {
  if (hasFilters) {
    return (
      <div className="py-12 text-center">
        <svg
          className="mx-auto h-12 w-12 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <h3 className="mt-4 text-lg font-medium text-gray-900">No bookmarks found</h3>
        <p className="mt-2 text-sm text-gray-500">
          Try adjusting your search or filter to find what you're looking for.
        </p>
      </div>
    )
  }

  return (
    <div className="py-12 text-center">
      <svg
        className="mx-auto h-12 w-12 text-gray-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
        />
      </svg>
      <h3 className="mt-4 text-lg font-medium text-gray-900">No bookmarks yet</h3>
      <p className="mt-2 text-sm text-gray-500">
        Get started by adding your first bookmark.
      </p>
      <button
        onClick={onAddBookmark}
        className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        Add Bookmark
      </button>
    </div>
  )
}

/**
 * Error state component.
 */
function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }): ReactNode {
  return (
    <div className="py-12 text-center">
      <svg
        className="mx-auto h-12 w-12 text-red-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <h3 className="mt-4 text-lg font-medium text-gray-900">Failed to load bookmarks</h3>
      <p className="mt-2 text-sm text-gray-500">{message}</p>
      <button
        onClick={onRetry}
        className="mt-4 rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
      >
        Try Again
      </button>
    </div>
  )
}

/**
 * Bookmarks page - main view for managing bookmarks.
 *
 * Features:
 * - List bookmarks with pagination
 * - Search by text (title, description, URL, content)
 * - Filter by tags (AND/OR modes)
 * - Sort by date or title
 * - Add, edit, delete bookmarks
 * - Keyboard shortcuts
 * - URL state for shareable filters
 */
export function Bookmarks(): ReactNode {
  const [searchParams, setSearchParams] = useSearchParams()
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingBookmark, setEditingBookmark] = useState<Bookmark | null>(null)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Hooks for data
  const {
    bookmarks,
    total,
    isLoading,
    error,
    fetchBookmarks,
    createBookmark,
    updateBookmark,
    deleteBookmark,
    fetchMetadata,
  } = useBookmarks()

  const { tags: tagSuggestions, fetchTags } = useTags()

  // Parse URL params
  const searchQuery = searchParams.get('q') || ''
  const selectedTagsRaw = searchParams.getAll('tags')
  // Memoize selectedTags to prevent infinite re-renders (getAll returns new array each time)
  const selectedTags = useMemo(() => selectedTagsRaw, [selectedTagsRaw.join(',')])
  const tagMatch = (searchParams.get('tag_match') as 'all' | 'any') || 'all'
  const sortBy = (searchParams.get('sort_by') as 'created_at' | 'title') || 'created_at'
  const sortOrder = (searchParams.get('sort_order') as 'asc' | 'desc') || 'desc'
  const offset = parseInt(searchParams.get('offset') || '0', 10)

  // Derive has_filters for empty state
  const hasFilters = searchQuery.length > 0 || selectedTags.length > 0

  // Build search params object
  const currentParams: BookmarkSearchParams = useMemo(
    () => ({
      q: searchQuery || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined,
      tag_match: selectedTags.length > 0 ? tagMatch : undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      offset,
      limit: DEFAULT_LIMIT,
    }),
    [searchQuery, selectedTags, tagMatch, sortBy, sortOrder, offset]
  )

  // Fetch bookmarks when params change
  useEffect(() => {
    fetchBookmarks(currentParams)
  }, [fetchBookmarks, currentParams])

  // Fetch tags on mount
  useEffect(() => {
    fetchTags()
  }, [fetchTags])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onNewBookmark: () => setShowAddModal(true),
    onFocusSearch: () => searchInputRef.current?.focus(),
    onEscape: () => {
      if (showAddModal) setShowAddModal(false)
      else if (editingBookmark) setEditingBookmark(null)
      else if (showShortcuts) setShowShortcuts(false)
    },
    onShowShortcuts: () => setShowShortcuts(true),
  })

  // Update URL params
  const updateParams = useCallback(
    (updates: Partial<BookmarkSearchParams>) => {
      const newParams = new URLSearchParams(searchParams)

      // Handle each param
      if ('q' in updates) {
        if (updates.q) {
          newParams.set('q', updates.q)
        } else {
          newParams.delete('q')
        }
      }

      if ('tags' in updates) {
        newParams.delete('tags')
        updates.tags?.forEach((tag) => newParams.append('tags', tag))
      }

      if ('tag_match' in updates) {
        if (updates.tag_match && updates.tag_match !== 'all') {
          newParams.set('tag_match', updates.tag_match)
        } else {
          newParams.delete('tag_match')
        }
      }

      if ('sort_by' in updates) {
        if (updates.sort_by && updates.sort_by !== 'created_at') {
          newParams.set('sort_by', updates.sort_by)
        } else {
          newParams.delete('sort_by')
        }
      }

      if ('sort_order' in updates) {
        if (updates.sort_order && updates.sort_order !== 'desc') {
          newParams.set('sort_order', updates.sort_order)
        } else {
          newParams.delete('sort_order')
        }
      }

      if ('offset' in updates) {
        if (updates.offset && updates.offset > 0) {
          newParams.set('offset', String(updates.offset))
        } else {
          newParams.delete('offset')
        }
      }

      setSearchParams(newParams, { replace: true })
    },
    [searchParams, setSearchParams]
  )

  // Handlers
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      updateParams({ q: e.target.value, offset: 0 })
    },
    [updateParams]
  )

  const handleTagClick = useCallback(
    (tag: string) => {
      if (!selectedTags.includes(tag)) {
        updateParams({ tags: [...selectedTags, tag], offset: 0 })
      }
    },
    [selectedTags, updateParams]
  )

  const handleRemoveTag = useCallback(
    (tagToRemove: string) => {
      updateParams({
        tags: selectedTags.filter((t) => t !== tagToRemove),
        offset: 0,
      })
    },
    [selectedTags, updateParams]
  )

  const handleTagMatchChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      updateParams({ tag_match: e.target.value as 'all' | 'any' })
    },
    [updateParams]
  )

  const handleSortChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value
      const [newSortBy, newSortOrder] = value.split('-') as ['created_at' | 'title', 'asc' | 'desc']
      updateParams({ sort_by: newSortBy, sort_order: newSortOrder })
    },
    [updateParams]
  )

  const handlePageChange = useCallback(
    (newOffset: number) => {
      updateParams({ offset: newOffset })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    [updateParams]
  )

  const handleAddBookmark = async (data: BookmarkCreate | BookmarkUpdate): Promise<void> => {
    setIsSubmitting(true)
    try {
      await createBookmark(data as BookmarkCreate)
      setShowAddModal(false)
      toast.success('Bookmark added')
      fetchBookmarks(currentParams)
      fetchTags()
    } catch (err) {
      // Check for duplicate URL error (409 Conflict)
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosError = err as { response?: { status?: number; data?: { detail?: string } } }
        if (axiosError.response?.status === 409) {
          toast.error(axiosError.response.data?.detail || 'A bookmark with this URL already exists')
          throw err
        }
      }
      toast.error('Failed to add bookmark')
      throw err
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleEditBookmark = async (data: BookmarkCreate | BookmarkUpdate): Promise<void> => {
    if (!editingBookmark) return

    setIsSubmitting(true)
    try {
      await updateBookmark(editingBookmark.id, data as BookmarkUpdate)
      setEditingBookmark(null)
      toast.success('Bookmark updated')
      fetchBookmarks(currentParams)
      fetchTags()
    } catch (err) {
      // Check for duplicate URL error (409 Conflict)
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosError = err as { response?: { status?: number; data?: { detail?: string } } }
        if (axiosError.response?.status === 409) {
          toast.error(axiosError.response.data?.detail || 'A bookmark with this URL already exists')
          throw err
        }
      }
      toast.error('Failed to update bookmark')
      throw err
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteBookmark = async (bookmark: Bookmark): Promise<void> => {
    if (!confirm(`Delete "${bookmark.title || bookmark.url}"?`)) return

    try {
      await deleteBookmark(bookmark.id)
      toast.success('Bookmark deleted')
      fetchBookmarks(currentParams)
      fetchTags()
    } catch (err) {
      toast.error('Failed to delete bookmark')
    }
  }

  const handleFetchMetadata = async (url: string): Promise<{
    title: string | null
    description: string | null
    error: string | null
  }> => {
    const result = await fetchMetadata(url)
    return {
      title: result.title,
      description: result.description,
      error: result.error,
    }
  }

  // Pagination calculations
  const totalPages = Math.ceil(total / DEFAULT_LIMIT)
  const currentPage = Math.floor(offset / DEFAULT_LIMIT) + 1
  const hasMore = offset + bookmarks.length < total

  // Render
  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Your Bookmarks</h1>
          <p className="mt-1 text-sm text-gray-500">
            {total} bookmark{total !== 1 ? 's' : ''}
            {hasFilters && ' matching your filters'}
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Bookmark
        </button>
      </div>

      {/* Search and filters */}
      <div className="mb-6 space-y-4">
        {/* Search input */}
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
            placeholder="Search bookmarks... (press / to focus)"
            className="w-full rounded-md border border-gray-300 py-2 pl-10 pr-4 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Filter row */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Selected tags */}
          {selectedTags.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-gray-500">Tags:</span>
              {selectedTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => handleRemoveTag(tag)}
                  className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-sm font-medium text-blue-800 hover:bg-blue-200"
                >
                  {tag}
                  <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              ))}

              {/* Tag match selector */}
              {selectedTags.length > 1 && (
                <select
                  value={tagMatch}
                  onChange={handleTagMatchChange}
                  className="rounded border border-gray-300 bg-white px-2 py-1 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="all">Match all</option>
                  <option value="any">Match any</option>
                </select>
              )}
            </div>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Sort selector */}
          <select
            value={`${sortBy}-${sortOrder}`}
            onChange={handleSortChange}
            className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="created_at-desc">Newest first</option>
            <option value="created_at-asc">Oldest first</option>
            <option value="title-asc">Title A-Z</option>
            <option value="title-desc">Title Z-A</option>
          </select>

          {/* Shortcuts hint */}
          <button
            onClick={() => setShowShortcuts(true)}
            className="text-xs text-gray-400 hover:text-gray-600"
            title="Keyboard shortcuts"
          >
            <kbd className="rounded border border-gray-300 bg-gray-100 px-1.5 py-0.5 font-mono text-xs">
              ?
            </kbd>
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading && bookmarks.length === 0 ? (
        <LoadingSpinner />
      ) : error ? (
        <ErrorState message={error} onRetry={() => fetchBookmarks(currentParams)} />
      ) : bookmarks.length === 0 ? (
        <EmptyState hasFilters={hasFilters} onAddBookmark={() => setShowAddModal(true)} />
      ) : (
        <>
          {/* Bookmark list */}
          <div className="space-y-4">
            {bookmarks.map((bookmark) => (
              <BookmarkCard
                key={bookmark.id}
                bookmark={bookmark}
                onEdit={setEditingBookmark}
                onDelete={handleDeleteBookmark}
                onTagClick={handleTagClick}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-between border-t border-gray-200 pt-4">
              <button
                onClick={() => handlePageChange(Math.max(0, offset - DEFAULT_LIMIT))}
                disabled={offset === 0}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Previous
              </button>

              <span className="text-sm text-gray-500">
                Page {currentPage} of {totalPages}
              </span>

              <button
                onClick={() => handlePageChange(offset + DEFAULT_LIMIT)}
                disabled={!hasMore}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* Add bookmark modal */}
      <BookmarkModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        tagSuggestions={tagSuggestions}
        onSubmit={handleAddBookmark}
        onFetchMetadata={handleFetchMetadata}
        isSubmitting={isSubmitting}
      />

      {/* Edit bookmark modal */}
      <BookmarkModal
        isOpen={!!editingBookmark}
        onClose={() => setEditingBookmark(null)}
        bookmark={editingBookmark || undefined}
        tagSuggestions={tagSuggestions}
        onSubmit={handleEditBookmark}
        onFetchMetadata={handleFetchMetadata}
        isSubmitting={isSubmitting}
      />

      {/* Shortcuts dialog */}
      <ShortcutsDialog
        isOpen={showShortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </div>
  )
}
