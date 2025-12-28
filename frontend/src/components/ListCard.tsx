/**
 * List card component for displaying a content list with its filter expression.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { ContentList, ContentType, FilterExpression } from '../types'
import { EditIcon, BookmarkIcon, NoteIcon } from './icons'
import { ConfirmDeleteButton } from './ui'
import { SORT_LABELS, type SortByOption } from '../constants/sortOptions'

interface ListCardProps {
  list: ContentList
  onEdit: (list: ContentList) => void
  onDelete: (list: ContentList) => Promise<void>
}

/**
 * Render filter expression as tag badges.
 * Groups are shown with AND between tags, OR between groups.
 */
function FilterExpressionDisplay({ expr }: { expr: FilterExpression }): ReactNode {
  if (!expr.groups || expr.groups.length === 0) {
    return <span className="text-sm text-gray-400">No filters</span>
  }

  const nonEmptyGroups = expr.groups.filter((group) => group.tags && group.tags.length > 0)

  if (nonEmptyGroups.length === 0) {
    return <span className="text-sm text-gray-400">No filters</span>
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      {nonEmptyGroups.map((group, groupIndex) => (
        <div key={groupIndex} className="flex items-center gap-1">
          {groupIndex > 0 && (
            <span className="text-xs text-gray-400 mx-0.5">or</span>
          )}
          {group.tags.map((tag, tagIndex) => (
            <div key={tag} className="flex items-center gap-1">
              {tagIndex > 0 && (
                <span className="text-xs text-gray-400">+</span>
              )}
              <span className="badge-secondary">{tag}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

/**
 * Display content type icons for the list.
 * Shows bookmark icon, note icon, or both based on content_types.
 */
function ContentTypesDisplay({ contentTypes }: { contentTypes: ContentType[] }): ReactNode {
  const hasBookmarks = contentTypes.includes('bookmark')
  const hasNotes = contentTypes.includes('note')

  // If both types, show nothing (default/shared)
  if (hasBookmarks && hasNotes) {
    return null
  }

  return (
    <div className="flex items-center gap-1" title={hasBookmarks ? 'Bookmarks only' : 'Notes only'}>
      {hasBookmarks && (
        <span className="text-blue-500">
          <BookmarkIcon className="h-4 w-4" />
        </span>
      )}
      {hasNotes && (
        <span className="text-amber-500">
          <NoteIcon className="h-4 w-4" />
        </span>
      )}
    </div>
  )
}

/**
 * Format sort order for display.
 * Shows: "Date Added (newest first)" or "Title (A-Z)"
 */
function formatSortOrder(sortBy: string | null, sortAscending: boolean | null): string | null {
  if (!sortBy) {
    return null
  }

  const label = SORT_LABELS[sortBy as SortByOption] || sortBy

  if (sortAscending === null) {
    return label
  }

  // Special handling for title (A-Z / Z-A)
  if (sortBy === 'title') {
    return `${label} (${sortAscending ? 'A-Z' : 'Z-A'})`
  }

  // For date fields (oldest/newest)
  return `${label} (${sortAscending ? 'oldest' : 'newest'})`
}

/**
 * List card with edit and delete actions.
 */
export function ListCard({ list, onEdit, onDelete }: ListCardProps): ReactNode {
  const [isDeleting, setIsDeleting] = useState(false)

  const handleDelete = async (): Promise<void> => {
    setIsDeleting(true)
    try {
      await onDelete(list)
    } finally {
      setIsDeleting(false)
    }
  }

  const sortDisplay = formatSortOrder(list.default_sort_by, list.default_sort_ascending)

  return (
    <div className="flex items-center justify-between p-4 list-item-hover gap-3">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <ContentTypesDisplay contentTypes={list.content_types} />
        <h3 className="font-medium text-gray-900 whitespace-nowrap">{list.name}</h3>
        <FilterExpressionDisplay expr={list.filter_expression} />
      </div>
      {sortDisplay && (
        <span className="text-xs text-gray-500 whitespace-nowrap">
          {sortDisplay}
        </span>
      )}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onEdit(list)}
          className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          title="Edit list"
        >
          <EditIcon />
        </button>
        <ConfirmDeleteButton
          onConfirm={handleDelete}
          isDeleting={isDeleting}
          title="Delete list"
        />
      </div>
    </div>
  )
}
