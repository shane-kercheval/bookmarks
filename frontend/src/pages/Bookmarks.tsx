/**
 * Bookmarks page - main bookmark list view with search, filter, and CRUD operations.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { useBookmarks } from '../hooks/useBookmarks'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useBookmarkView } from '../hooks/useBookmarkView'
import { useBookmarkUrlParams } from '../hooks/useBookmarkUrlParams'
import { useEffectiveSort, getViewKey } from '../hooks/useEffectiveSort'
import { useTagsStore } from '../stores/tagsStore'
import { useListsStore } from '../stores/listsStore'
import { useTagFilterStore } from '../stores/tagFilterStore'
import { SORT_LABELS, type SortByOption } from '../constants/sortOptions'
import { BookmarkCard } from '../components/BookmarkCard'
import { BookmarkModal } from '../components/BookmarkModal'
import { TagFilterInput } from '../components/TagFilterInput'
import { LoadingSpinnerCentered, ErrorState, EmptyState } from '../components/ui'
import {
  SearchIcon,
  BookmarkIcon,
  PlusIcon,
  CloseIconFilled,
  ArchiveIcon,
  FolderIcon,
  TrashIcon,
} from '../components/icons'
import type { Bookmark, BookmarkListItem, BookmarkCreate, BookmarkUpdate, BookmarkSearchParams } from '../types'
import { getFirstGroupTags } from '../utils'

/** Default pagination limit */
const DEFAULT_LIMIT = 50

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
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingBookmark, setEditingBookmark] = useState<Bookmark | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [pastedUrl, setPastedUrl] = useState<string | undefined>(undefined)
  const [loadingBookmarkId, setLoadingBookmarkId] = useState<number | null>(null)

  // Hooks for data
  const {
    bookmarks,
    total,
    isLoading,
    error,
    hasInitiallyLoaded,
    fetchBookmarks,
    fetchBookmark,
    createBookmark,
    updateBookmark,
    deleteBookmark,
    restoreBookmark,
    archiveBookmark,
    unarchiveBookmark,
    fetchMetadata,
    trackBookmarkUsage,
  } = useBookmarks()

  const { tags: tagSuggestions, fetchTags } = useTagsStore()
  const lists = useListsStore((state) => state.lists)

  // Tag filters from global store (persists across navigation)
  const {
    selectedTags,
    tagMatch,
    addTag,
    removeTag,
    setTagMatch,
    clearFilters: clearTagFilters,
  } = useTagFilterStore()

  // Route-based view
  const { currentView, currentListId } = useBookmarkView()

  // URL params for search and pagination (sort now from useEffectiveSort, tags from store)
  const {
    searchQuery,
    offset,
    updateParams,
  } = useBookmarkUrlParams()

  // Per-view sort with priority chain: user override > list default > view default
  const currentList = useMemo(
    () => (currentListId ? lists.find((l) => l.id === currentListId) : undefined),
    [currentListId, lists]
  )
  const viewKey = useMemo(() => getViewKey(currentView, currentListId), [currentView, currentListId])
  const listDefault = useMemo(
    () =>
      currentList
        ? { sortBy: currentList.default_sort_by, ascending: currentList.default_sort_ascending }
        : undefined,
    [currentList]
  )
  const { sortBy, sortOrder, setSort, availableSortOptions } = useEffectiveSort(
    viewKey,
    currentView,
    listDefault
  )

  // Derive hasFilters from search query and tag store
  const hasFilters = searchQuery.length > 0 || selectedTags.length > 0

  // Get initial tags from current list's first filter group (for pre-populating new bookmarks)
  const initialTagsFromList = useMemo(() => {
    if (!currentListId) return undefined
    const currentList = lists.find((l) => l.id === currentListId)
    return getFirstGroupTags(currentList)
  }, [currentListId, lists])

  // Debounce search query to avoid excessive API calls while typing
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 300)

  // Build search params object (uses debounced search query)
  const currentParams: BookmarkSearchParams = useMemo(
    () => ({
      q: debouncedSearchQuery || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined,
      tag_match: selectedTags.length > 0 ? tagMatch : undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      offset,
      limit: DEFAULT_LIMIT,
      view: currentView,
      list_id: currentListId,
    }),
    [debouncedSearchQuery, selectedTags, tagMatch, sortBy, sortOrder, offset, currentView, currentListId]
  )

  // Fetch bookmarks when params change
  useEffect(() => {
    fetchBookmarks(currentParams)
  }, [fetchBookmarks, currentParams])

  // Keyboard shortcuts (page-specific - global shortcuts are in Layout)
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
      else if (document.activeElement === searchInputRef.current) {
        searchInputRef.current?.blur()
      }
    },
    onPasteUrl: (url) => {
      // Only allow adding bookmarks from active view
      if (currentView === 'active') {
        setPastedUrl(url)
        setShowAddModal(true)
      }
    },
  })

  // Handlers for search/filter/sort changes
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      updateParams({ q: e.target.value, offset: 0 })
    },
    [updateParams]
  )

  const handleTagClick = useCallback(
    (tag: string) => {
      if (!selectedTags.includes(tag)) {
        addTag(tag)
        updateParams({ offset: 0 })
      }
    },
    [selectedTags, addTag, updateParams]
  )

  const handleRemoveTag = useCallback(
    (tagToRemove: string) => {
      removeTag(tagToRemove)
      updateParams({ offset: 0 })
    },
    [removeTag, updateParams]
  )

  const handleTagMatchChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setTagMatch(e.target.value as 'all' | 'any')
    },
    [setTagMatch]
  )

  const handleClearTagFilters = useCallback(() => {
    clearTagFilters()
    updateParams({ offset: 0 })
  }, [clearTagFilters, updateParams])

  const handleSortChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value
      const [newSortBy, newSortOrder] = value.split('-') as [SortByOption, 'asc' | 'desc']
      setSort(newSortBy, newSortOrder)
    },
    [setSort]
  )

  const handlePageChange = useCallback(
    (newOffset: number) => {
      updateParams({ offset: newOffset })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    [updateParams]
  )

  // --------------------------------------------------------------------------
  // Bookmark Action Handlers
  //
  // Note: These handlers have intentional variation that makes extraction difficult:
  // - handleAddBookmark: Special 409 handling for archived URLs with unarchive action
  // - handleEditBookmark: Special 409 handling for duplicate URLs
  // - handleDeleteBookmark: Different behavior for trash view (permanent) vs others (soft)
  // - Archive/unarchive/restore: Undo toasts with async callbacks
  //
  // Each handler follows a similar pattern (try/action/refresh/toast/catch) but the
  // variations in error handling, success messages, and undo functionality mean that
  // extracting a generic wrapper would either be too rigid or add complexity without
  // improving readability. The explicit handlers make each operation's behavior clear.
  // --------------------------------------------------------------------------

  const handleEditClick = async (bookmark: BookmarkListItem): Promise<void> => {
    // Prevent re-fetching if already loading this bookmark
    if (loadingBookmarkId === bookmark.id) return

    setLoadingBookmarkId(bookmark.id)
    try {
      const fullBookmark = await fetchBookmark(bookmark.id)
      setEditingBookmark(fullBookmark)
    } catch {
      toast.error('Failed to load bookmark')
    } finally {
      setLoadingBookmarkId(null)
    }
  }

  const handleAddBookmark = async (data: BookmarkCreate | BookmarkUpdate): Promise<void> => {
    setIsSubmitting(true)
    try {
      await createBookmark(data as BookmarkCreate)
      setShowAddModal(false)
      setPastedUrl(undefined)
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
                          setPastedUrl(undefined)
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

  const handleDeleteBookmark = async (bookmark: BookmarkListItem): Promise<void> => {
    // In trash view, use permanent delete (confirmation handled by ConfirmDeleteButton)
    if (currentView === 'deleted') {
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

  const handleArchiveBookmark = async (bookmark: BookmarkListItem): Promise<void> => {
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

  const handleUnarchiveBookmark = async (bookmark: BookmarkListItem): Promise<void> => {
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

  const handleRestoreBookmark = async (bookmark: BookmarkListItem): Promise<void> => {
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
    content: string | null
    error: string | null
  }> => {
    const result = await fetchMetadata(url)
    return {
      title: result.title,
      description: result.description,
      content: result.content,
      error: result.error,
    }
  }

  // Pagination calculations
  const totalPages = Math.ceil(total / DEFAULT_LIMIT)
  const currentPage = Math.floor(offset / DEFAULT_LIMIT) + 1
  const hasMore = offset + bookmarks.length < total

  // Render content based on state
  const renderContent = (): ReactNode => {
    // Show loading on initial load or when loading with no cached data
    if (!hasInitiallyLoaded || (isLoading && bookmarks.length === 0)) {
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

      // Active view - check if it's a list view
      if (currentListId) {
        // Custom list with no matching bookmarks
        const currentList = lists.find((l) => l.id === currentListId)
        return (
          <EmptyState
            icon={<FolderIcon />}
            title="No bookmarks match this list"
            description={`Add bookmarks with the tags defined in "${currentList?.name || 'this list'}" to see them here.`}
          />
        )
      }

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
              sortBy={sortBy}
              onEdit={currentView !== 'deleted' ? handleEditClick : undefined}
              onDelete={handleDeleteBookmark}
              onArchive={currentView === 'active' ? handleArchiveBookmark : undefined}
              onUnarchive={currentView === 'archived' ? handleUnarchiveBookmark : undefined}
              onRestore={currentView === 'deleted' ? handleRestoreBookmark : undefined}
              onTagClick={handleTagClick}
              onLinkClick={(b) => trackBookmarkUsage(b.id)}
              isLoading={loadingBookmarkId === bookmark.id}
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

  // Determine if we should show add button (only for active views, not archived/trash)
  const showAddButton = currentView === 'active'

  return (
    <div>
      {/* Search and filters */}
      <div className="mb-6 space-y-3">
        {/* Add button (only in active view), search, and sort row */}
        <div className="flex items-center gap-3">
          {showAddButton && (
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
          <TagFilterInput
            suggestions={tagSuggestions}
            selectedTags={selectedTags}
            onTagSelect={handleTagClick}
            placeholder="Filter by tag..."
          />
          <div className="flex items-center gap-1">
            <select
              value={`${sortBy}-${sortOrder}`}
              onChange={handleSortChange}
              className="rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2.5 text-sm focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5"
            >
              {availableSortOptions.map((option) => (
                <optgroup key={option} label={SORT_LABELS[option]}>
                  <option value={`${option}-desc`}>{SORT_LABELS[option]} ↓</option>
                  <option value={`${option}-asc`}>{SORT_LABELS[option]} ↑</option>
                </optgroup>
              ))}
            </select>
          </div>
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
                <CloseIconFilled />
              </button>
            ))}
            {selectedTags.length > 1 && (
              <>
                <select
                  value={tagMatch}
                  onChange={handleTagMatchChange}
                  className="rounded-lg border border-gray-200 bg-gray-50/50 px-2 py-1 text-xs focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5"
                >
                  <option value="all">Match all</option>
                  <option value="any">Match any</option>
                </select>
                <button
                  onClick={handleClearTagFilters}
                  className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
                >
                  Clear
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      {renderContent()}

      {/* Add bookmark modal */}
      <BookmarkModal
        isOpen={showAddModal}
        onClose={() => {
          setShowAddModal(false)
          setPastedUrl(undefined)
        }}
        tagSuggestions={tagSuggestions}
        onSubmit={handleAddBookmark}
        onFetchMetadata={handleFetchMetadata}
        isSubmitting={isSubmitting}
        initialUrl={pastedUrl}
        initialTags={initialTagsFromList}
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

    </div>
  )
}
