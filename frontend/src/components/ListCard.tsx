/**
 * List card component for displaying a bookmark list with its filter expression.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { BookmarkList, FilterExpression } from '../types'
import { EditIcon, TrashIcon } from './icons'

interface ListCardProps {
  list: BookmarkList
  onEdit: (list: BookmarkList) => void
  onDelete: (list: BookmarkList) => Promise<void>
}

/**
 * Format filter expression for display.
 * Shows: (tag1 AND tag2) OR (tag3)
 */
function formatFilterExpression(expr: FilterExpression): string {
  if (!expr.groups || expr.groups.length === 0) {
    return 'No filters'
  }

  const groupStrings = expr.groups
    .filter((group) => group.tags && group.tags.length > 0)
    .map((group) => {
      if (group.tags.length === 1) {
        return group.tags[0]
      }
      return `(${group.tags.join(' AND ')})`
    })

  if (groupStrings.length === 0) {
    return 'No filters'
  }

  return groupStrings.join(' OR ')
}

/**
 * List card with edit and delete actions.
 */
export function ListCard({ list, onEdit, onDelete }: ListCardProps): ReactNode {
  const [isDeleting, setIsDeleting] = useState(false)

  const handleDelete = async (): Promise<void> => {
    if (!confirm(`Delete list "${list.name}"? This action cannot be undone.`)) {
      return
    }

    setIsDeleting(true)
    try {
      await onDelete(list)
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="flex items-center justify-between p-4 list-item-hover">
      <div className="min-w-0 flex-1">
        <h3 className="font-medium text-gray-900">{list.name}</h3>
        <p className="mt-1 text-sm text-gray-500 truncate">
          {formatFilterExpression(list.filter_expression)}
        </p>
      </div>
      <div className="ml-4 flex items-center gap-2">
        <button
          onClick={() => onEdit(list)}
          className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          title="Edit list"
        >
          <EditIcon />
        </button>
        <button
          onClick={handleDelete}
          disabled={isDeleting}
          className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
          title="Delete list"
        >
          <TrashIcon />
        </button>
      </div>
    </div>
  )
}
