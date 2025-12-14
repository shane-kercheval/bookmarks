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
import { LoadingSpinnerCentered, ErrorState, EmptyState } from '../components/ui'
import type { Bookmark, BookmarkCreate, BookmarkUpdate, BookmarkSearchParams } from '../types'

/** Default pagination limit */
const DEFAULT_LIMIT = 50

/** Search icon SVG */
const SearchIcon = (): ReactNode => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
    />
  </svg>
)

/** Bookmark icon for empty state */
const BookmarkIcon = (): ReactNode => (
  <svg className="h-full w-full" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
    />
  </svg>
)

/** Plus icon for add button */
const PlusIcon = (): ReactNode => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
)

/** Close icon for tag removal */
const CloseIcon = (): ReactNode => (
  <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
    <path
      fillRule="evenodd"
      d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
      clipRule="evenodd"
    />
  </svg>
)

/** Archive icon for empty state */
const ArchiveIcon = (): ReactNode => (
  <svg className="h-full w-full" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
    />
  </svg>
)

/** Trash icon for empty state */
const TrashIcon = (): ReactNode => (
  <svg className="h-full w-full" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
    />
  </svg>
)

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
    restoreBookmark,
    archiveBookmark,
    unarchiveBookmark,
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
  const currentView = (searchParams.get('view') as 'active' | 'archived' | 'deleted') || 'active'

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
      view: currentView,
    }),
    [searchQuery, selectedTags, tagMatch, sortBy, sortOrder, offset, currentView]
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
    onNewBookmark: () => {
      // Only allow adding bookmarks from active view
      if (currentView === 'active') {
        setShowAddModal(true)
      }
    },
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

      if ('view' in updates) {
        if (updates.view && updates.view !== 'active') {
          newParams.set('view', updates.view)
        } else {
          newParams.delete('view')
        }
        // Reset pagination when switching views
        newParams.delete('offset')
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
        const axiosError = err as {
          response?: {
            status?: number
            data?: {
              detail?: string | {
                message?: string
                error_code?: string
                existing_bookmark_id?: number
              }
            }
          }
        }
        if (axiosError.response?.status === 409) {
          const detail = axiosError.response.data?.detail
          // Check if it's the structured error response for archived URL
          if (typeof detail === 'object' && detail?.error_code === 'ARCHIVED_URL_EXISTS' && detail?.existing_bookmark_id) {
            const bookmarkId = detail.existing_bookmark_id
            toast.error(
              (t) => (
                <span className="flex items-center gap-2">
                  This URL is in your archive.
                  <button
                    onClick={() => {
                      toast.dismiss(t.id)
                      unarchiveBookmark(bookmarkId)
                        .then(() => {
                          setShowAddModal(false)
                          fetchBookmarks(currentParams)
                          fetchTags()
                          toast.success('Bookmark unarchived')
                        })
                        .catch(() => {
                          toast.error('Failed to unarchive bookmark')
                        })
                    }}
                    className="font-medium underline"
                  >
                    Unarchive
                  </button>
                </span>
              ),
              { duration: 8000 }
            )
          } else {
            // Regular duplicate URL error
            const message = typeof detail === 'string' ? detail : detail?.message || 'A bookmark with this URL already exists'
            toast.error(message)
          }
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
    // In trash view, use permanent delete with confirmation
    if (currentView === 'deleted') {
      if (!confirm('Permanently delete this bookmark? This cannot be undone.')) return

      try {
        await deleteBookmark(bookmark.id, true) // permanent=true
        fetchBookmarks(currentParams)
        fetchTags()
        toast.success('Bookmark permanently deleted')
      } catch {
        toast.error('Failed to delete bookmark')
      }
      return
    }

    // In active/archived views, use soft delete with undo toast
    try {
      await deleteBookmark(bookmark.id)
      fetchBookmarks(currentParams)
      fetchTags()
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark deleted.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                restoreBookmark(bookmark.id)
                  .then(() => {
                    fetchBookmarks(currentParams)
                    fetchTags()
                    toast.success('Bookmark restored')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The bookmark may have been modified.")
                  })
              }}
              className="font-medium underline"
            >
              Undo
            </button>
          </span>
        ),
        { duration: 5000 }
      )
    } catch {
      toast.error('Failed to delete bookmark')
    }
  }

  const handleArchiveBookmark = async (bookmark: Bookmark): Promise<void> => {
    try {
      await archiveBookmark(bookmark.id)
      fetchBookmarks(currentParams)
      fetchTags()
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark archived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                unarchiveBookmark(bookmark.id)
                  .then(() => {
                    fetchBookmarks(currentParams)
                    fetchTags()
                    toast.success('Bookmark unarchived')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The bookmark may have been modified.")
                  })
              }}
              className="font-medium underline"
            >
              Undo
            </button>
          </span>
        ),
        { duration: 5000 }
      )
    } catch {
      toast.error('Failed to archive bookmark')
    }
  }

  const handleUnarchiveBookmark = async (bookmark: Bookmark): Promise<void> => {
    try {
      await unarchiveBookmark(bookmark.id)
      fetchBookmarks(currentParams)
      fetchTags()
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark unarchived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                archiveBookmark(bookmark.id)
                  .then(() => {
                    fetchBookmarks(currentParams)
                    fetchTags()
                    toast.success('Bookmark archived')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The bookmark may have been modified.")
                  })
              }}
              className="font-medium underline"
            >
              Undo
            </button>
          </span>
        ),
        { duration: 5000 }
      )
    } catch {
      toast.error('Failed to unarchive bookmark')
    }
  }

  const handleRestoreBookmark = async (bookmark: Bookmark): Promise<void> => {
    try {
      await restoreBookmark(bookmark.id)
      fetchBookmarks(currentParams)
      fetchTags()
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark restored.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                deleteBookmark(bookmark.id)
                  .then(() => {
                    fetchBookmarks(currentParams)
                    fetchTags()
                    toast.success('Bookmark moved to trash')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The bookmark may have been modified.")
                  })
              }}
              className="font-medium underline"
            >
              Undo
            </button>
          </span>
        ),
        { duration: 5000 }
      )
    } catch {
      toast.error('Failed to restore bookmark')
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

  // Render content based on state
  const renderContent = (): ReactNode => {
    if (isLoading && bookmarks.length === 0) {
      return <LoadingSpinnerCentered label="Loading bookmarks..." />
    }

    if (error) {
      return <ErrorState message={error} onRetry={() => fetchBookmarks(currentParams)} />
    }

    if (bookmarks.length === 0) {
      // Different empty states based on current view
      if (currentView === 'archived') {
        if (hasFilters) {
          return (
            <EmptyState
              icon={<SearchIcon />}
              title="No archived bookmarks found"
              description="Try adjusting your search or filter."
            />
          )
        }
        return (
          <EmptyState
            icon={<ArchiveIcon />}
            title="No archived bookmarks"
            description="Bookmarks you archive will appear here."
          />
        )
      }

      if (currentView === 'deleted') {
        if (hasFilters) {
          return (
            <EmptyState
              icon={<SearchIcon />}
              title="No deleted bookmarks found"
              description="Try adjusting your search or filter."
            />
          )
        }
        return (
          <EmptyState
            icon={<TrashIcon />}
            title="Trash is empty"
            description="Items in trash are permanently deleted after 30 days."
          />
        )
      }

      // Active view
      if (hasFilters) {
        return (
          <EmptyState
            icon={<SearchIcon />}
            title="No bookmarks found"
            description="Try adjusting your search or filter to find what you're looking for."
          />
        )
      }
      return (
        <EmptyState
          icon={<BookmarkIcon />}
          title="No bookmarks yet"
          description="Get started by adding your first bookmark."
          action={{ label: 'Add Bookmark', onClick: () => setShowAddModal(true) }}
        />
      )
    }

    return (
      <>
        {/* Bookmark list */}
        <div>
          {bookmarks.map((bookmark) => (
            <BookmarkCard
              key={bookmark.id}
              bookmark={bookmark}
              view={currentView}
              onEdit={currentView !== 'deleted' ? setEditingBookmark : undefined}
              onDelete={handleDeleteBookmark}
              onArchive={currentView === 'active' ? handleArchiveBookmark : undefined}
              onUnarchive={currentView === 'archived' ? handleUnarchiveBookmark : undefined}
              onRestore={currentView === 'deleted' ? handleRestoreBookmark : undefined}
              onTagClick={handleTagClick}
            />
          ))}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-8 flex items-center justify-between border-t border-gray-100 pt-4">
            <button
              onClick={() => handlePageChange(Math.max(0, offset - DEFAULT_LIMIT))}
              disabled={offset === 0}
              className="btn-secondary"
            >
              Previous
            </button>

            <span className="text-sm text-gray-400">
              Page {currentPage} of {totalPages}
            </span>

            <button
              onClick={() => handlePageChange(offset + DEFAULT_LIMIT)}
              disabled={!hasMore}
              className="btn-secondary"
            >
              Next
            </button>
          </div>
        )}
      </>
    )
  }

  // Handler for view tab change
  const handleViewChange = useCallback(
    (newView: 'active' | 'archived' | 'deleted') => {
      updateParams({ view: newView })
    },
    [updateParams]
  )

  return (
    <div>
      {/* View tabs */}
      <div className="mb-4 border-b border-gray-200">
        <nav className="-mb-px flex gap-4" aria-label="Tabs">
          <button
            onClick={() => handleViewChange('active')}
            className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
              currentView === 'active'
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            All Bookmarks
          </button>
          <button
            onClick={() => handleViewChange('archived')}
            className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
              currentView === 'archived'
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Archived
          </button>
          <button
            onClick={() => handleViewChange('deleted')}
            className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors ${
              currentView === 'deleted'
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Trash
          </button>
        </nav>
      </div>

      {/* Search and filters */}
      <div className="mb-6 space-y-3">
        {/* Add button (only in active view), search, and sort row */}
        <div className="flex items-center gap-3">
          {currentView === 'active' && (
            <button
              onClick={() => setShowAddModal(true)}
              className="btn-primary shrink-0 p-2.5"
              title="Add bookmark"
              aria-label="Add bookmark"
            >
              <PlusIcon />
            </button>
          )}
          <div className="relative flex-1">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              <SearchIcon />
            </div>
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={handleSearchChange}
              placeholder="Search bookmarks..."
              className="input pl-10"
            />
          </div>
          <select
            value={`${sortBy}-${sortOrder}`}
            onChange={handleSortChange}
            className="rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2.5 text-sm focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5"
          >
            <option value="created_at-desc">Newest first</option>
            <option value="created_at-asc">Oldest first</option>
            <option value="title-asc">Title A-Z</option>
            <option value="title-desc">Title Z-A</option>
          </select>
        </div>

        {/* Selected tags filter */}
        {selectedTags.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-400">Filtering by:</span>
            {selectedTags.map((tag) => (
              <button
                key={tag}
                onClick={() => handleRemoveTag(tag)}
                className="badge-primary inline-flex items-center gap-1 hover:bg-blue-100 transition-colors"
              >
                {tag}
                <CloseIcon />
              </button>
            ))}
            {selectedTags.length > 1 && (
              <select
                value={tagMatch}
                onChange={handleTagMatchChange}
                className="rounded-lg border border-gray-200 bg-gray-50/50 px-2 py-1 text-xs focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5"
              >
                <option value="all">Match all</option>
                <option value="any">Match any</option>
              </select>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      {renderContent()}

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
