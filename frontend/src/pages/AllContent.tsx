/**
 * AllContent page - unified view for all content types (bookmarks + notes).
 *
 * Used for the shared views: All, Archived, Trash, and custom shared lists.
 * Displays both bookmarks and notes in a single unified list.
 */
import { useState, useCallback, useRef, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useContentQuery } from '../hooks/useContentQuery'
import { useContentView } from '../hooks/useContentView'
import { useBookmarks } from '../hooks/useBookmarks'
import {
  useDeleteBookmark,
  useRestoreBookmark,
  useArchiveBookmark,
  useUnarchiveBookmark,
} from '../hooks/useBookmarkMutations'
import {
  useDeleteNote,
  useRestoreNote,
  useArchiveNote,
  useUnarchiveNote,
} from '../hooks/useNoteMutations'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useEffectiveSort, getViewKey } from '../hooks/useEffectiveSort'
import { useTagsStore } from '../stores/tagsStore'
import { useTagFilterStore } from '../stores/tagFilterStore'
import { useUIPreferencesStore, PAGE_SIZE_OPTIONS } from '../stores/uiPreferencesStore'
import type { PageSize } from '../stores/uiPreferencesStore'
import { SORT_LABELS, type SortByOption } from '../constants/sortOptions'
import { BookmarkCard } from '../components/BookmarkCard'
import { NoteCard } from '../components/NoteCard'
import { TagFilterInput } from '../components/TagFilterInput'
import { LoadingSpinnerCentered, ErrorState, EmptyState } from '../components/ui'
import {
  SearchIcon,
  CloseIconFilled,
  ArchiveIcon,
  TrashIcon,
  SharedIcon,
} from '../components/icons'
import type { ContentListItem, ContentSearchParams, BookmarkListItem, NoteListItem } from '../types'

/**
 * AllContent page - unified view for all content types.
 *
 * Features:
 * - List bookmarks and notes together with unified pagination
 * - Search by text (title, description, content)
 * - Filter by tags (AND/OR modes)
 * - Sort by date or title
 * - Navigate to edit pages for individual items
 */
export function AllContent(): ReactNode {
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Local search state
  const [searchQuery, setSearchQuery] = useState('')
  const [offset, setOffset] = useState(0)

  // Non-cacheable utilities
  const { trackBookmarkUsage } = useBookmarks()

  // Mutation hooks
  const deleteBookmarkMutation = useDeleteBookmark()
  const restoreBookmarkMutation = useRestoreBookmark()
  const archiveBookmarkMutation = useArchiveBookmark()
  const unarchiveBookmarkMutation = useUnarchiveBookmark()
  const deleteNoteMutation = useDeleteNote()
  const restoreNoteMutation = useRestoreNote()
  const archiveNoteMutation = useArchiveNote()
  const unarchiveNoteMutation = useUnarchiveNote()

  const { tags: tagSuggestions } = useTagsStore()
  const { pageSize, setPageSize } = useUIPreferencesStore()

  // Tag filters from global store
  const {
    selectedTags,
    tagMatch,
    addTag,
    removeTag,
    setTagMatch,
    clearFilters: clearTagFilters,
  } = useTagFilterStore()

  // Route-based view and list ID
  const { currentView, currentListId } = useContentView('/app/content')

  // Per-view sort
  const viewKey = useMemo(() => getViewKey(currentView, currentListId), [currentView, currentListId])
  const { sortBy, sortOrder, setSort, availableSortOptions } = useEffectiveSort(
    viewKey,
    currentView,
    undefined
  )

  // Derive hasFilters from search query and tag store
  const hasFilters = searchQuery.length > 0 || selectedTags.length > 0

  // Debounce search query
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 300)

  // Build search params
  const currentParams: ContentSearchParams = useMemo(
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

  // Fetch content with TanStack Query
  const {
    data: queryData,
    isLoading,
    error: queryError,
    refetch,
  } = useContentQuery(currentParams)

  // Extract data from query result
  const items = queryData?.items ?? []
  const total = queryData?.total ?? 0
  const error = queryError ? (queryError instanceof Error ? queryError.message : 'Failed to fetch content') : null

  // Handlers
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchQuery(e.target.value)
      setOffset(0)
    },
    []
  )

  const handleTagClick = useCallback(
    (tag: string) => {
      if (!selectedTags.includes(tag)) {
        addTag(tag)
        setOffset(0)
      }
    },
    [selectedTags, addTag]
  )

  const handleRemoveTag = useCallback(
    (tagToRemove: string) => {
      removeTag(tagToRemove)
      setOffset(0)
    },
    [removeTag]
  )

  const handleTagMatchChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setTagMatch(e.target.value as 'all' | 'any')
    },
    [setTagMatch]
  )

  const handleClearTagFilters = useCallback(() => {
    clearTagFilters()
    setOffset(0)
  }, [clearTagFilters])

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
      setOffset(newOffset)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
    []
  )

  // Bookmark action handlers
  const handleEditBookmark = (bookmark: BookmarkListItem): void => {
    navigate(`/app/bookmarks/${bookmark.id}/edit`)
  }

  const handleDeleteBookmark = async (bookmark: BookmarkListItem): Promise<void> => {
    if (currentView === 'deleted') {
      try {
        await deleteBookmarkMutation.mutateAsync({ id: bookmark.id, permanent: true })
      } catch {
        toast.error('Failed to delete bookmark')
      }
      return
    }

    try {
      await deleteBookmarkMutation.mutateAsync({ id: bookmark.id })
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark deleted.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                restoreBookmarkMutation.mutateAsync(bookmark.id)
                  .catch(() => toast.error("Couldn't undo"))
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
      await archiveBookmarkMutation.mutateAsync(bookmark.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Bookmark archived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                unarchiveBookmarkMutation.mutateAsync(bookmark.id)
                  .catch(() => toast.error("Couldn't undo"))
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
      await unarchiveBookmarkMutation.mutateAsync(bookmark.id)
    } catch {
      toast.error('Failed to unarchive bookmark')
    }
  }

  const handleRestoreBookmark = async (bookmark: BookmarkListItem): Promise<void> => {
    try {
      await restoreBookmarkMutation.mutateAsync(bookmark.id)
    } catch {
      toast.error('Failed to restore bookmark')
    }
  }

  // Note action handlers
  const handleViewNote = (note: NoteListItem): void => {
    navigate(`/app/notes/${note.id}`)
  }

  const handleEditNote = (note: NoteListItem): void => {
    navigate(`/app/notes/${note.id}/edit`)
  }

  const handleDeleteNote = async (note: NoteListItem): Promise<void> => {
    if (currentView === 'deleted') {
      try {
        await deleteNoteMutation.mutateAsync({ id: note.id, permanent: true })
      } catch {
        toast.error('Failed to delete note')
      }
      return
    }

    try {
      await deleteNoteMutation.mutateAsync({ id: note.id })
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Note deleted.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                restoreNoteMutation.mutateAsync(note.id)
                  .catch(() => toast.error("Couldn't undo"))
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
      toast.error('Failed to delete note')
    }
  }

  const handleArchiveNote = async (note: NoteListItem): Promise<void> => {
    try {
      await archiveNoteMutation.mutateAsync(note.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Note archived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                unarchiveNoteMutation.mutateAsync(note.id)
                  .catch(() => toast.error("Couldn't undo"))
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
      toast.error('Failed to archive note')
    }
  }

  const handleUnarchiveNote = async (note: NoteListItem): Promise<void> => {
    try {
      await unarchiveNoteMutation.mutateAsync(note.id)
    } catch {
      toast.error('Failed to unarchive note')
    }
  }

  const handleRestoreNote = async (note: NoteListItem): Promise<void> => {
    try {
      await restoreNoteMutation.mutateAsync(note.id)
    } catch {
      toast.error('Failed to restore note')
    }
  }

  // Convert ContentListItem to type-specific item for card components
  const toBookmarkListItem = (item: ContentListItem): BookmarkListItem => ({
    id: item.id,
    url: item.url || '',
    title: item.title,
    description: item.description,
    summary: null,
    tags: item.tags,
    created_at: item.created_at,
    updated_at: item.updated_at,
    last_used_at: item.last_used_at,
    deleted_at: item.deleted_at,
    archived_at: item.archived_at,
  })

  const toNoteListItem = (item: ContentListItem): NoteListItem => ({
    id: item.id,
    title: item.title || '',
    description: item.description,
    tags: item.tags,
    created_at: item.created_at,
    updated_at: item.updated_at,
    last_used_at: item.last_used_at,
    deleted_at: item.deleted_at,
    archived_at: item.archived_at,
    version: item.version || 1,
  })

  // Pagination calculations
  const totalPages = Math.ceil(total / pageSize)
  const currentPage = Math.floor(offset / pageSize) + 1
  const hasMore = offset + items.length < total

  // Render content based on state
  const renderContent = (): ReactNode => {
    if (isLoading) {
      return <LoadingSpinnerCentered label="Loading content..." />
    }

    if (error) {
      return <ErrorState message={error} onRetry={() => refetch()} />
    }

    if (items.length === 0) {
      if (currentView === 'archived') {
        if (hasFilters) {
          return (
            <EmptyState
              icon={<SearchIcon />}
              title="No archived content found"
              description="Try adjusting your search or filter."
            />
          )
        }
        return (
          <EmptyState
            icon={<ArchiveIcon />}
            title="No archived content"
            description="Content you archive will appear here."
          />
        )
      }

      if (currentView === 'deleted') {
        if (hasFilters) {
          return (
            <EmptyState
              icon={<SearchIcon />}
              title="No deleted content found"
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

      if (hasFilters) {
        return (
          <EmptyState
            icon={<SearchIcon />}
            title="No content found"
            description="Try adjusting your search or filter."
          />
        )
      }

      return (
        <EmptyState
          icon={<SharedIcon />}
          title="No content yet"
          description="Create bookmarks or notes to see them here."
        />
      )
    }

    return (
      <>
        {/* Content list */}
        <div>
          {items.map((item) => (
            item.type === 'bookmark' ? (
              <BookmarkCard
                key={`bookmark-${item.id}`}
                bookmark={toBookmarkListItem(item)}
                view={currentView}
                sortBy={sortBy}
                onEdit={currentView !== 'deleted' ? handleEditBookmark : undefined}
                onDelete={handleDeleteBookmark}
                onArchive={currentView === 'active' ? handleArchiveBookmark : undefined}
                onUnarchive={currentView === 'archived' ? handleUnarchiveBookmark : undefined}
                onRestore={currentView === 'deleted' ? handleRestoreBookmark : undefined}
                onTagClick={handleTagClick}
                onLinkClick={(b) => trackBookmarkUsage(b.id)}
              />
            ) : (
              <NoteCard
                key={`note-${item.id}`}
                note={toNoteListItem(item)}
                view={currentView}
                sortBy={sortBy}
                onView={handleViewNote}
                onEdit={currentView !== 'deleted' ? handleEditNote : undefined}
                onDelete={handleDeleteNote}
                onArchive={currentView === 'active' ? handleArchiveNote : undefined}
                onUnarchive={currentView === 'archived' ? handleUnarchiveNote : undefined}
                onRestore={currentView === 'deleted' ? handleRestoreNote : undefined}
                onTagClick={handleTagClick}
              />
            )
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
                  setOffset(0)
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

  return (
    <div>
      {/* Search and filters */}
      <div className="mb-6 space-y-3">
        {/* Search and sort row */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              <SearchIcon />
            </div>
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={handleSearchChange}
              placeholder="Search all content..."
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
    </div>
  )
}
