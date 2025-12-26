/**
 * Bookmarks page - main bookmark list view with search, filter, and CRUD operations.
 */
import { useState, useCallback, useRef, useMemo } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { useBookmarks } from '../hooks/useBookmarks'
import { useBookmarksQuery } from '../hooks/useBookmarksQuery'
import {
  useCreateBookmark,
  useUpdateBookmark,
  useDeleteBookmark,
  useRestoreBookmark,
  useArchiveBookmark,
  useUnarchiveBookmark,
} from '../hooks/useBookmarkMutations'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useBookmarkView } from '../hooks/useBookmarkView'
import { useBookmarkUrlParams } from '../hooks/useBookmarkUrlParams'
import { useEffectiveSort, getViewKey } from '../hooks/useEffectiveSort'
import { useTagsStore } from '../stores/tagsStore'
import { useListsStore } from '../stores/listsStore'
import { useTagFilterStore } from '../stores/tagFilterStore'
import { useUIPreferencesStore, PAGE_SIZE_OPTIONS } from '../stores/uiPreferencesStore'
import type { PageSize } from '../stores/uiPreferencesStore'
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

  // Non-cacheable utilities from useBookmarks
  const { fetchBookmark, fetchMetadata, trackBookmarkUsage } = useBookmarks()

  // Mutation hooks with automatic cache invalidation
  const createMutation = useCreateBookmark()
  const updateMutation = useUpdateBookmark()
  const deleteMutation = useDeleteBookmark()
  const restoreMutation = useRestoreBookmark()
  const archiveMutation = useArchiveBookmark()
  const unarchiveMutation = useUnarchiveBookmark()

  const { tags: tagSuggestions } = useTagsStore()
  const lists = useListsStore((state) => state.lists)
  const { pageSize, setPageSize } = useUIPreferencesStore()

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
      limit: pageSize,
      view: currentView,
      list_id: currentListId,
    }),
    [debouncedSearchQuery, selectedTags, tagMatch, sortBy, sortOrder, offset, pageSize, currentView, currentListId]
  )

  // Fetch bookmarks with TanStack Query caching
  const {
    data: queryData,
    isLoading,
    error: queryError,
    refetch,
  } = useBookmarksQuery(currentParams)

  // Extract data from query result
  const bookmarks = queryData?.items ?? []
  const total = queryData?.total ?? 0
  const error = queryError ? (queryError instanceof Error ? queryError.message : 'Failed to fetch bookmarks') : null

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
      await createMutation.mutateAsync(data as BookmarkCreate)
      setShowAddModal(false)
      setPastedUrl(undefined)
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
                      unarchiveMutation.mutateAsync(bookmarkId)
                        .then(() => {
                          setShowAddModal(false)
                          setPastedUrl(undefined)
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
      await updateMutation.mutateAsync({ id: editingBookmark.id, data: data as BookmarkUpdate })
      setEditingBookmark(null)
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
        await deleteMutation.mutateAsync({ id: bookmark.id, permanent: true })
      } catch {
        toast.error('Failed to delete bookmark')
      }
      return
    }

    // In active/archived views, use soft delete with undo toast
    try {
      await deleteMutation.mutateAsync({ id: bookmark.id })
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark deleted.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                restoreMutation.mutateAsync(bookmark.id)
                  .then(() => {
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
      await archiveMutation.mutateAsync(bookmark.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark archived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                unarchiveMutation.mutateAsync(bookmark.id)
                  .then(() => {
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
      await unarchiveMutation.mutateAsync(bookmark.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark unarchived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                archiveMutation.mutateAsync(bookmark.id)
                  .then(() => {
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
      await restoreMutation.mutateAsync(bookmark.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark restored.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                deleteMutation.mutateAsync({ id: bookmark.id })
                  .then(() => {
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

  const handleTagRemove = async (bookmark: BookmarkListItem, tag: string): Promise<void> => {
    const newTags = bookmark.tags.filter((t) => t !== tag)
    try {
      await updateMutation.mutateAsync({ id: bookmark.id, data: { tags: newTags } })
    } catch {
      toast.error('Failed to remove tag')
    }
  }

  const handleCancelScheduledArchive = async (bookmark: BookmarkListItem): Promise<void> => {
    try {
      await updateMutation.mutateAsync({ id: bookmark.id, data: { archived_at: null } })
    } catch {
      toast.error('Failed to cancel scheduled archive')
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
  const totalPages = Math.ceil(total / pageSize)
  const currentPage = Math.floor(offset / pageSize) + 1
  const hasMore = offset + bookmarks.length < total

  // Render content based on state
  const renderContent = (): ReactNode => {
    // Show loading spinner whenever fetching bookmarks
    if (isLoading) {
      return <LoadingSpinnerCentered label="Loading bookmarks..." />
    }

    if (error) {
      return <ErrorState message={error} onRetry={() => refetch()} />
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
              onTagRemove={currentView !== 'deleted' ? handleTagRemove : undefined}
              onCancelScheduledArchive={currentView === 'active' ? handleCancelScheduledArchive : undefined}
              onLinkClick={(b) => trackBookmarkUsage(b.id)}
              isLoading={loadingBookmarkId === bookmark.id}
            />
          ))}
        </div>

        {/* Pagination */}
        {(totalPages > 1 || total > PAGE_SIZE_OPTIONS[0]) && (
          <div className="mt-8 flex items-center justify-between border-t border-gray-100 pt-4">
            <button
              onClick={() => handlePageChange(Math.max(0, offset - pageSize))}
              disabled={offset === 0}
              className="btn-secondary"
            >
              Previous
            </button>

            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400">
                Page {currentPage} of {totalPages}
              </span>
              <select
                value={pageSize}
                onChange={(e) => {
                  const newSize = Number(e.target.value) as PageSize
                  setPageSize(newSize)
                  updateParams({ offset: 0 })
                }}
                className="appearance-none cursor-pointer rounded-lg border border-gray-200 bg-gray-50/50 px-2 py-1 pr-6 text-xs focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5 bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[length:1rem_1rem] bg-[right_0.25rem_center] bg-no-repeat"
                title="Items per page"
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>{size} per page</option>
                ))}
              </select>
            </div>

            <button
              onClick={() => handlePageChange(offset + pageSize)}
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
              className="appearance-none cursor-pointer rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2.5 pr-8 text-sm focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5 bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[length:1.25rem_1.25rem] bg-[right_0.5rem_center] bg-no-repeat"
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
                  className="appearance-none cursor-pointer rounded-lg border border-gray-200 bg-gray-50/50 px-2 py-1 pr-6 text-xs focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5 bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[length:1rem_1rem] bg-[right_0.25rem_center] bg-no-repeat"
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
