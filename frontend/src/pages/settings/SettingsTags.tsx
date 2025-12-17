/**
 * Settings page for Tag management.
 *
 * Allows users to view all tags, rename them, and delete them.
 */
import { useEffect, useState } from 'react'
import type { ReactNode, FormEvent } from 'react'
import toast from 'react-hot-toast'
import { useTagsStore } from '../../stores/tagsStore'
import { LoadingSpinner } from '../../components/ui/LoadingSpinner'
import { validateTag, normalizeTag } from '../../utils'
import type { TagCount } from '../../types'

interface EditingState {
  tagName: string
  newName: string
  error: string | null
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
    if (!confirm(`Delete tag "${tag.name}"? This will remove it from all bookmarks.`)) {
      return
    }
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
        <td className="py-3 pr-4">
          <form onSubmit={handleSave} className="flex items-center gap-2">
            <input
              type="text"
              value={editingState.newName}
              onChange={(e) => onEditChange(e.target.value)}
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
        <td className="py-3 pr-4 text-center text-sm text-gray-500">{tag.count}</td>
        <td className="py-3 text-right">
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
      <td className="py-3 pr-4">
        <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-sm font-medium text-gray-700">
          {tag.name}
        </span>
      </td>
      <td className="py-3 pr-4 text-center text-sm text-gray-500">{tag.count}</td>
      <td className="py-3 text-right">
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onStartEdit}
            className="rounded px-2 py-1 text-sm text-gray-600 hover:bg-gray-100"
          >
            Rename
          </button>
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="rounded px-2 py-1 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            {isDeleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </td>
    </tr>
  )
}

/**
 * Tags management settings page.
 */
export function SettingsTags(): ReactNode {
  const { tags, isLoading, fetchTags, renameTag, deleteTag } = useTagsStore()
  const [editingState, setEditingState] = useState<EditingState | null>(null)

  useEffect(() => {
    fetchTags()
  }, [fetchTags])

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
      toast.success(`Tag renamed to "${normalized}"`)
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
      toast.success(`Tag "${tagName}" deleted`)
    } catch {
      toast.error('Failed to delete tag')
    }
  }

  // Separate tags with bookmarks from orphaned tags
  const activeTags = tags.filter((tag) => tag.count > 0)
  const orphanedTags = tags.filter((tag) => tag.count === 0)

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Tags</h1>
        <p className="mt-1 text-gray-500">
          Manage your tags. Rename or delete tags across all bookmarks.
        </p>
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
                    {activeTags.map((tag) => (
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
              </div>
            )}
          </section>

          {/* Orphaned Tags */}
          {orphanedTags.length > 0 && (
            <section>
              <h2 className="mb-2 text-lg font-semibold text-gray-900">
                Unused Tags ({orphanedTags.length})
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
                      <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-gray-500">
                        Bookmarks
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white px-4">
                    {orphanedTags.map((tag) => (
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
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
