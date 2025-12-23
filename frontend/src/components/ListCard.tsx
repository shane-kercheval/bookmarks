/**
 * List card component for displaying a bookmark list with its filter expression.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { BookmarkList, FilterExpression } from '../types'
import { EditIcon } from './icons'
import { ConfirmDeleteButton } from './ui'
import { SORT_LABELS, type SortByOption } from '../constants/sortOptions'

interface ListCardProps {
  list: BookmarkList
  onEdit: (list: BookmarkList) => void
  onDelete: (list: BookmarkList) => Promise<void>
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
