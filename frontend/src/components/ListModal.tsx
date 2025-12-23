/**
 * Modal for creating and editing bookmark lists.
 */
import { useState, useEffect } from 'react'
import type { ReactNode, FormEvent } from 'react'
import type { BookmarkList, BookmarkListCreate, BookmarkListUpdate, FilterExpression, TagCount } from '../types'
import { BASE_SORT_OPTIONS, SORT_LABELS, type BaseSortOption } from '../constants/sortOptions'
import { FilterExpressionBuilder } from './FilterExpressionBuilder'
import { Modal } from './ui/Modal'

interface ListModalProps {
  isOpen: boolean
  onClose: () => void
  list?: BookmarkList
  tagSuggestions: TagCount[]
  onCreate?: (data: BookmarkListCreate) => Promise<BookmarkList>
  onUpdate?: (id: number, data: BookmarkListUpdate) => Promise<BookmarkList>
}

/**
 * Create default empty filter expression.
 */
function createEmptyFilterExpression(): FilterExpression {
  return {
    groups: [{ tags: [], operator: 'AND' }],
    group_operator: 'OR',
  }
}

/**
 * Modal for creating/editing lists with filter expression builder.
 */
export function ListModal({
  isOpen,
  onClose,
  list,
  tagSuggestions,
  onCreate,
  onUpdate,
}: ListModalProps): ReactNode {
  const [name, setName] = useState('')
  const [filterExpression, setFilterExpression] = useState<FilterExpression>(createEmptyFilterExpression())
  const [defaultSortBy, setDefaultSortBy] = useState<BaseSortOption | null>(null)
  const [defaultSortAscending, setDefaultSortAscending] = useState<boolean>(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isEditing = !!list

  // Reset/populate form when modal opens
  // Note: Focus management is handled by the shared Modal component
  useEffect(() => {
    if (isOpen) {
      if (list) {
        setName(list.name)
        setFilterExpression(list.filter_expression)
        setDefaultSortBy((list.default_sort_by as BaseSortOption) || null)
        setDefaultSortAscending(list.default_sort_ascending ?? false)
      } else {
        setName('')
        setFilterExpression(createEmptyFilterExpression())
        setDefaultSortBy(null)
        setDefaultSortAscending(false)
      }
      setError(null)
    }
  }, [isOpen, list])

  const validateFilterExpression = (expr: FilterExpression): boolean => {
    // At least one group must have at least one tag
    return expr.groups.some((group) => group.tags && group.tags.length > 0)
  }

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()

    if (!name.trim()) {
      setError('List name is required')
      return
    }

    if (!validateFilterExpression(filterExpression)) {
      setError('At least one tag filter is required')
      return
    }

    // Clean up filter expression - remove empty groups
    const cleanedExpression: FilterExpression = {
      ...filterExpression,
      groups: filterExpression.groups.filter((g) => g.tags && g.tags.length > 0),
    }

    setIsSubmitting(true)
    setError(null)

    try {
      if (isEditing && onUpdate && list) {
        await onUpdate(list.id, {
          name: name.trim(),
          filter_expression: cleanedExpression,
          default_sort_by: defaultSortBy,
          default_sort_ascending: defaultSortBy ? defaultSortAscending : null,
        })
      } else if (onCreate) {
        await onCreate({
          name: name.trim(),
          filter_expression: cleanedExpression,
          default_sort_by: defaultSortBy,
          default_sort_ascending: defaultSortBy ? defaultSortAscending : null,
        })
      }
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save list')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit List' : 'Create List'}
      noPadding
    >
      <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        <div>
          <label htmlFor="list-name" className="block text-sm font-medium text-gray-700 mb-1">
            List Name
          </label>
          <input
            id="list-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Work Resources, Reading List"
            className="input"
            disabled={isSubmitting}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Filter Tags
          </label>
          <FilterExpressionBuilder
            value={filterExpression}
            onChange={setFilterExpression}
            tagSuggestions={tagSuggestions}
          />
        </div>

        <div>
          <label htmlFor="list-sort" className="block text-sm font-medium text-gray-700 mb-1">
            Default Sort
          </label>
          <div className="flex items-center gap-3">
            <select
              id="list-sort"
              value={defaultSortBy ?? ''}
              onChange={(e) => {
                const value = e.target.value as BaseSortOption | ''
                setDefaultSortBy(value || null)
                if (!value) {
                  setDefaultSortAscending(false)
                }
              }}
              className="flex-1 rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2 text-sm focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5"
              disabled={isSubmitting}
            >
              <option value="">System default (Last Used)</option>
              {BASE_SORT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {SORT_LABELS[option]}
                </option>
              ))}
            </select>
            {defaultSortBy && (
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={defaultSortAscending}
                  onChange={(e) => setDefaultSortAscending(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-gray-900 focus:ring-gray-900/10"
                  disabled={isSubmitting}
                />
                Ascending
              </label>
            )}
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary flex-1"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn-primary flex-1"
            disabled={isSubmitting || !name.trim()}
          >
            {isSubmitting ? 'Saving...' : isEditing ? 'Save Changes' : 'Create List'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
