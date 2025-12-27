/**
 * Notes page - main note list view with search, filter, and CRUD operations.
 */
import { useState, useCallback, useRef, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useNotes } from '../hooks/useNotes'
import { useNotesQuery } from '../hooks/useNotesQuery'
import {
  useUpdateNote,
  useDeleteNote,
  useRestoreNote,
  useArchiveNote,
  useUnarchiveNote,
} from '../hooks/useNoteMutations'
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useNoteView } from '../hooks/useNoteView'
import { useNoteUrlParams } from '../hooks/useNoteUrlParams'
import { useEffectiveSort, getViewKey } from '../hooks/useEffectiveSort'
import { useTagsStore } from '../stores/tagsStore'
import { useListsStore } from '../stores/listsStore'
import { useTagFilterStore } from '../stores/tagFilterStore'
import { useUIPreferencesStore, PAGE_SIZE_OPTIONS } from '../stores/uiPreferencesStore'
import type { PageSize } from '../stores/uiPreferencesStore'
import { SORT_LABELS, type SortByOption } from '../constants/sortOptions'
import { NoteCard } from '../components/NoteCard'
import { TagFilterInput } from '../components/TagFilterInput'
import { LoadingSpinnerCentered, ErrorState, EmptyState } from '../components/ui'
import {
  SearchIcon,
  NoteIcon,
  PlusIcon,
  CloseIconFilled,
  ArchiveIcon,
  FolderIcon,
  TrashIcon,
} from '../components/icons'
import type { NoteListItem, NoteSearchParams } from '../types'
import { getFirstGroupTags } from '../utils'


/**
 * Notes page - main view for managing notes.
 *
 * Features:
 * - List notes with pagination
 * - Search by text (title, description, content)
 * - Filter by tags (AND/OR modes)
 * - Sort by date or title
 * - Add, edit, delete notes
 * - Keyboard shortcuts
 * - URL state for shareable filters
 */
export function Notes(): ReactNode {
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Loading state for fetching full note
  const [loadingNoteId, setLoadingNoteId] = useState<number | null>(null)

  // Non-cacheable utilities from useNotes
  const { fetchNote } = useNotes()

  // Mutation hooks with automatic cache invalidation
  const updateMutation = useUpdateNote()
  const deleteMutation = useDeleteNote()
  const restoreMutation = useRestoreNote()
  const archiveMutation = useArchiveNote()
  const unarchiveMutation = useUnarchiveNote()

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
  const { currentView, currentListId } = useNoteView()

  // URL params for search and pagination
  const {
    searchQuery,
    offset,
    updateParams,
  } = useNoteUrlParams()

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

  // Get initial tags from current list's first filter group (for pre-populating new notes)
  const initialTagsFromList = useMemo(() => {
    if (!currentListId) return undefined
    const currentList = lists.find((l) => l.id === currentListId)
    return getFirstGroupTags(currentList)
  }, [currentListId, lists])

  // Debounce search query to avoid excessive API calls while typing
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 300)

  // Build search params object (uses debounced search query)
  const currentParams: NoteSearchParams = useMemo(
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

  // Fetch notes with TanStack Query caching
  const {
    data: queryData,
    isLoading,
    error: queryError,
    refetch,
  } = useNotesQuery(currentParams)

  // Extract data from query result
  const notes = queryData?.items ?? []
  const total = queryData?.total ?? 0
  const error = queryError ? (queryError instanceof Error ? queryError.message : 'Failed to fetch notes') : null

  // Keyboard shortcuts (page-specific)
  useKeyboardShortcuts({
    onNewBookmark: () => {
      // Reuse 'b' shortcut for new note on notes page
      // Only allow adding notes from active view
      if (currentView === 'active') {
        navigate('/app/notes/new')
      }
    },
    onFocusSearch: () => searchInputRef.current?.focus(),
    onEscape: () => {
      if (document.activeElement === searchInputRef.current) {
        searchInputRef.current?.blur()
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
  // Note Action Handlers
  // --------------------------------------------------------------------------

  const handleViewNote = useCallback(
    (note: NoteListItem): void => {
      navigate(`/app/notes/${note.id}`)
    },
    [navigate]
  )

  const handleEditClick = useCallback(
    async (note: NoteListItem): Promise<void> => {
      // Prevent re-fetching if already loading this note
      if (loadingNoteId === note.id) return

      setLoadingNoteId(note.id)
      try {
        // Fetch full note to ensure content is available
        await fetchNote(note.id)
        navigate(`/app/notes/${note.id}/edit`)
      } catch {
        toast.error('Failed to load note')
      } finally {
        setLoadingNoteId(null)
      }
    },
    [loadingNoteId, fetchNote, navigate]
  )

  const handleDeleteNote = async (note: NoteListItem): Promise<void> => {
    // In trash view, use permanent delete (confirmation handled by ConfirmDeleteButton)
    if (currentView === 'deleted') {
      try {
        await deleteMutation.mutateAsync({ id: note.id, permanent: true })
      } catch {
        toast.error('Failed to delete note')
      }
      return
    }

    // In active/archived views, use soft delete with undo toast
    try {
      await deleteMutation.mutateAsync({ id: note.id })
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Note deleted.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                restoreMutation.mutateAsync(note.id)
                  .then(() => {
                    toast.success('Note restored')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The note may have been modified.")
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
      toast.error('Failed to delete note')
    }
  }

  const handleArchiveNote = async (note: NoteListItem): Promise<void> => {
    try {
      await archiveMutation.mutateAsync(note.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Note archived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                unarchiveMutation.mutateAsync(note.id)
                  .then(() => {
                    toast.success('Note unarchived')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The note may have been modified.")
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
      toast.error('Failed to archive note')
    }
  }

  const handleUnarchiveNote = async (note: NoteListItem): Promise<void> => {
    try {
      await unarchiveMutation.mutateAsync(note.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Note unarchived.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                archiveMutation.mutateAsync(note.id)
                  .then(() => {
                    toast.success('Note archived')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The note may have been modified.")
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
      toast.error('Failed to unarchive note')
    }
  }

  const handleRestoreNote = async (note: NoteListItem): Promise<void> => {
    try {
      await restoreMutation.mutateAsync(note.id)
      toast.success(
        (t) => (
          <span className="flex items-center gap-2">
            Note restored.
            <button
              onClick={() => {
                toast.dismiss(t.id)
                deleteMutation.mutateAsync({ id: note.id })
                  .then(() => {
                    toast.success('Note moved to trash')
                  })
                  .catch(() => {
                    toast.error("Couldn't undo. The note may have been modified.")
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
      toast.error('Failed to restore note')
    }
  }

  const handleTagRemove = async (note: NoteListItem, tag: string): Promise<void> => {
    const newTags = note.tags.filter((t) => t !== tag)
    try {
      await updateMutation.mutateAsync({ id: note.id, data: { tags: newTags } })
    } catch {
      toast.error('Failed to remove tag')
    }
  }

  // Pagination calculations
  const totalPages = Math.ceil(total / pageSize)
  const currentPage = Math.floor(offset / pageSize) + 1
  const hasMore = offset + notes.length < total

  // Render content based on state
  const renderContent = (): ReactNode => {
    // Show loading spinner whenever fetching notes
    if (isLoading) {
      return <LoadingSpinnerCentered label="Loading notes..." />
    }

    if (error) {
      return <ErrorState message={error} onRetry={() => refetch()} />
    }

    if (notes.length === 0) {
      // Different empty states based on current view
      if (currentView === 'archived') {
        if (hasFilters) {
          return (
            <EmptyState
              icon={<SearchIcon />}
              title="No archived notes found"
              description="Try adjusting your search or filter."
            />
          )
        }
        return (
          <EmptyState
            icon={<ArchiveIcon />}
            title="No archived notes"
            description="Notes you archive will appear here."
          />
        )
      }

      if (currentView === 'deleted') {
        if (hasFilters) {
          return (
            <EmptyState
              icon={<SearchIcon />}
              title="No deleted notes found"
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
        // Custom list with no matching notes
        const currentList = lists.find((l) => l.id === currentListId)
        return (
          <EmptyState
            icon={<FolderIcon />}
            title="No notes match this list"
            description={`Add notes with the tags defined in "${currentList?.name || 'this list'}" to see them here.`}
          />
        )
      }

      if (hasFilters) {
        return (
          <EmptyState
            icon={<SearchIcon />}
            title="No notes found"
            description="Try adjusting your search or filter to find what you're looking for."
          />
        )
      }
      return (
        <EmptyState
          icon={<NoteIcon />}
          title="No notes yet"
          description="Get started by creating your first note."
          action={{ label: 'New Note', onClick: () => navigate('/app/notes/new', { state: { initialTags: initialTagsFromList } }) }}
        />
      )
    }

    return (
      <>
        {/* Note list */}
        <div>
          {notes.map((note) => (
            <NoteCard
              key={note.id}
              note={note}
              view={currentView}
              sortBy={sortBy}
              onView={handleViewNote}
              onEdit={currentView !== 'deleted' ? handleEditClick : undefined}
              onDelete={handleDeleteNote}
              onArchive={currentView === 'active' ? handleArchiveNote : undefined}
              onUnarchive={currentView === 'archived' ? handleUnarchiveNote : undefined}
              onRestore={currentView === 'deleted' ? handleRestoreNote : undefined}
              onTagClick={handleTagClick}
              onTagRemove={currentView !== 'deleted' ? handleTagRemove : undefined}
              isLoading={loadingNoteId === note.id}
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
              onClick={() => navigate('/app/notes/new', { state: { initialTags: initialTagsFromList } })}
              className="btn-primary shrink-0 p-2.5"
              title="New note"
              aria-label="New note"
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
              placeholder="Search notes..."
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
                  <option value={`${option}-desc`}>{SORT_LABELS[option]} &#8595;</option>
                  <option value={`${option}-asc`}>{SORT_LABELS[option]} &#8593;</option>
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
