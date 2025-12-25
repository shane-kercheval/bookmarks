/**
 * Settings page for Tag management.
 *
 * Allows users to view all tags, rename them, and delete them.
 */
import { useState, useMemo } from 'react'
import type { ReactNode, FormEvent } from 'react'
import toast from 'react-hot-toast'
import { useTagsStore } from '../../stores/tagsStore'
import { LoadingSpinner, ConfirmDeleteButton } from '../../components/ui'
import { EditIcon } from '../../components/icons'
import { validateTag, normalizeTag, sortTags } from '../../utils'
import type { TagSortOption } from '../../utils'
import type { TagCount } from '../../types'

const ITEMS_PER_PAGE = 15

interface EditingState {
  tagName: string
  newName: string
  error: string | null
}

interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
}

function Pagination({ currentPage, totalPages, onPageChange }: PaginationProps): ReactNode {
  if (totalPages <= 1) return null

  return (
    <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-4 py-3">
      <span className="text-sm text-gray-500">
        Page {currentPage} of {totalPages}
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className="rounded border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="rounded border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  )
}

interface TagRowProps {
  tag: TagCount
  isEditing: boolean
  editingState: EditingState | null
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => Promise<void>
  onEditChange: (value: string) => void
  onDelete: () => Promise<void>
  showCount?: boolean
}

function TagRow({
  tag,
  isEditing,
  editingState,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onEditChange,
  onDelete,
  showCount = true,
}: TagRowProps): ReactNode {
  const [isDeleting, setIsDeleting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const handleSave = async (e: FormEvent): Promise<void> => {
    e.preventDefault()
    setIsSaving(true)
    try {
      await onSaveEdit()
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (): Promise<void> => {
    setIsDeleting(true)
    try {
      await onDelete()
    } finally {
      setIsDeleting(false)
    }
  }

  if (isEditing && editingState) {
    return (
      <tr className="border-b border-gray-100">
        <td className="py-3 pl-4 pr-4">
          <form onSubmit={handleSave} className="flex items-center gap-2">
            <input
              type="text"
              value={editingState.newName}
              onChange={(e) => onEditChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault()
                  onCancelEdit()
                }
              }}
              className={`w-full rounded border px-2 py-1 text-sm ${
                editingState.error ? 'border-red-300' : 'border-gray-300'
              } focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500`}
              autoFocus
              disabled={isSaving}
            />
          </form>
          {editingState.error && (
            <p className="mt-1 text-xs text-red-500">{editingState.error}</p>
          )}
        </td>
        {showCount && (
          <td className="py-3 pr-4 text-center text-sm text-gray-500">{tag.count}</td>
        )}
        <td className="py-3 pr-4 text-right">
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={handleSave}
              disabled={isSaving || !!editingState.error}
              className="rounded px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50"
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={onCancelEdit}
              disabled={isSaving}
              className="rounded px-2 py-1 text-sm text-gray-500 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50">
      <td className="py-3 pl-4 pr-4">
        <span className="badge-secondary">
          {tag.name}
        </span>
      </td>
      {showCount && (
        <td className="py-3 pr-4 text-center text-sm text-gray-500">{tag.count}</td>
      )}
      <td className="py-3 pr-4 text-right">
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={onStartEdit}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="Rename tag"
          >
            <EditIcon />
          </button>
          <ConfirmDeleteButton
            onConfirm={handleDelete}
            isDeleting={isDeleting}
            title="Delete tag"
          />
        </div>
      </td>
    </tr>
  )
}

/**
 * Tags management settings page.
 */
export function SettingsTags(): ReactNode {
  const { tags, isLoading, renameTag, deleteTag } = useTagsStore()
  const [editingState, setEditingState] = useState<EditingState | null>(null)
  const [sortOption, setSortOption] = useState<TagSortOption>('name-asc')
  const [activeTagsPage, setActiveTagsPage] = useState(1)
  const [unusedTagsPage, setUnusedTagsPage] = useState(1)

  const handleSortChange = (newSortOption: TagSortOption): void => {
    setSortOption(newSortOption)
    setActiveTagsPage(1)
    setUnusedTagsPage(1)
  }

  const handleStartEdit = (tagName: string): void => {
    setEditingState({
      tagName,
      newName: tagName,
      error: null,
    })
  }

  const handleCancelEdit = (): void => {
    setEditingState(null)
  }

  const handleEditChange = (value: string): void => {
    if (!editingState) return
    const normalized = normalizeTag(value)
    const error = normalized ? validateTag(normalized) : null
    setEditingState({
      ...editingState,
      newName: value,
      error,
    })
  }

  const handleSaveEdit = async (): Promise<void> => {
    if (!editingState) return
    const normalized = normalizeTag(editingState.newName)

    // Validate
    const error = validateTag(normalized)
    if (error) {
      setEditingState({ ...editingState, error })
      return
    }

    // No change
    if (normalized === editingState.tagName) {
      setEditingState(null)
      return
    }

    try {
      await renameTag(editingState.tagName, normalized)
      setEditingState(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to rename tag'
      if (message.includes('409') || message.toLowerCase().includes('already exists')) {
        setEditingState({ ...editingState, error: 'A tag with this name already exists' })
      } else {
        toast.error(message)
      }
    }
  }

  const handleDelete = async (tagName: string): Promise<void> => {
    try {
      await deleteTag(tagName)
    } catch {
      toast.error('Failed to delete tag')
    }
  }

  // Separate, sort, and paginate tags
  const activeTags = useMemo(() => {
    const filtered = tags.filter((tag) => tag.count > 0)
    return sortTags(filtered, sortOption)
  }, [tags, sortOption])

  const unusedTags = useMemo(() => {
    const filtered = tags.filter((tag) => tag.count === 0)
    return sortTags(filtered, sortOption)
  }, [tags, sortOption])

  const activeTagsTotalPages = Math.ceil(activeTags.length / ITEMS_PER_PAGE)
  const unusedTagsTotalPages = Math.ceil(unusedTags.length / ITEMS_PER_PAGE)

  const paginatedActiveTags = useMemo(() => {
    const start = (activeTagsPage - 1) * ITEMS_PER_PAGE
    return activeTags.slice(start, start + ITEMS_PER_PAGE)
  }, [activeTags, activeTagsPage])

  const paginatedUnusedTags = useMemo(() => {
    const start = (unusedTagsPage - 1) * ITEMS_PER_PAGE
    return unusedTags.slice(start, start + ITEMS_PER_PAGE)
  }, [unusedTags, unusedTagsPage])

  return (
    <div className="max-w-3xl">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tags</h1>
          <p className="mt-1 text-gray-500">
            Manage your tags. Rename or delete tags across all bookmarks.
          </p>
        </div>
        <select
          value={sortOption}
          onChange={(e) => handleSortChange(e.target.value as TagSortOption)}
          className="appearance-none cursor-pointer rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2 pr-8 text-sm focus:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/5 bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[length:1.25rem_1.25rem] bg-[right_0.5rem_center] bg-no-repeat"
        >
          <option value="name-asc">Name ↑</option>
          <option value="name-desc">Name ↓</option>
          <option value="count-desc">Count ↓</option>
          <option value="count-asc">Count ↑</option>
        </select>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner />
        </div>
      ) : tags.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-8 text-center">
          <p className="text-gray-500">No tags yet. Tags will appear here once you add them to bookmarks.</p>
        </div>
      ) : (
        <>
          {/* Active Tags */}
          <section className="mb-8">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">
              Active Tags ({activeTags.length})
            </h2>
            {activeTags.length === 0 ? (
              <p className="text-sm text-gray-500">No active tags.</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-gray-200">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                        Tag
                      </th>
                      <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-gray-500">
                        Bookmarks
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white px-4">
                    {paginatedActiveTags.map((tag) => (
                      <TagRow
                        key={tag.name}
                        tag={tag}
                        isEditing={editingState?.tagName === tag.name}
                        editingState={editingState?.tagName === tag.name ? editingState : null}
                        onStartEdit={() => handleStartEdit(tag.name)}
                        onCancelEdit={handleCancelEdit}
                        onSaveEdit={handleSaveEdit}
                        onEditChange={handleEditChange}
                        onDelete={() => handleDelete(tag.name)}
                      />
                    ))}
                  </tbody>
                </table>
                <Pagination
                  currentPage={activeTagsPage}
                  totalPages={activeTagsTotalPages}
                  onPageChange={setActiveTagsPage}
                />
              </div>
            )}
          </section>

          {/* Inactive Tags */}
          {unusedTags.length > 0 && (
            <section>
              <h2 className="mb-2 text-lg font-semibold text-gray-900">
                Inactive Tags ({unusedTags.length})
              </h2>
              <p className="mb-4 text-sm text-gray-500">
                These tags are not used by any active bookmarks. They may be associated with archived or deleted bookmarks.
              </p>
              <div className="overflow-hidden rounded-lg border border-gray-200">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                        Tag
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white px-4">
                    {paginatedUnusedTags.map((tag) => (
                      <TagRow
                        key={tag.name}
                        tag={tag}
                        isEditing={editingState?.tagName === tag.name}
                        editingState={editingState?.tagName === tag.name ? editingState : null}
                        onStartEdit={() => handleStartEdit(tag.name)}
                        onCancelEdit={handleCancelEdit}
                        onSaveEdit={handleSaveEdit}
                        onEditChange={handleEditChange}
                        onDelete={() => handleDelete(tag.name)}
                        showCount={false}
                      />
                    ))}
                  </tbody>
                </table>
                <Pagination
                  currentPage={unusedTagsPage}
                  totalPages={unusedTagsTotalPages}
                  onPageChange={setUnusedTagsPage}
                />
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
