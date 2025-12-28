/**
 * List manager component for displaying and managing content lists.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { ContentList, ContentListCreate, ContentListUpdate, TagCount } from '../types'
import { ListCard } from './ListCard'
import { ListModal } from './ListModal'
import { FolderIcon } from './icons'

interface ListManagerProps {
  lists: ContentList[]
  isLoading: boolean
  tagSuggestions: TagCount[]
  onCreate: (data: ContentListCreate) => Promise<ContentList>
  onUpdate: (id: number, data: ContentListUpdate) => Promise<ContentList>
  onDelete: (id: number) => Promise<void>
  /** If true, opens the create modal (controlled by parent) */
  isCreateModalOpen?: boolean
  /** Called when create modal should close */
  onCreateModalClose?: () => void
}

/**
 * List manager with create, edit, and delete functionality.
 */
export function ListManager({
  lists,
  isLoading,
  tagSuggestions,
  onCreate,
  onUpdate,
  onDelete,
  isCreateModalOpen = false,
  onCreateModalClose,
}: ListManagerProps): ReactNode {
  const [editingList, setEditingList] = useState<ContentList | null>(null)

  const isModalOpen = isCreateModalOpen || editingList !== null

  const handleEdit = (list: ContentList): void => {
    setEditingList(list)
  }

  const handleDelete = async (list: ContentList): Promise<void> => {
    await onDelete(list.id)
  }

  const handleCloseModal = (): void => {
    if (editingList) {
      // Was editing - just clear the editing state
      setEditingList(null)
    } else {
      // Was creating - notify parent to close
      onCreateModalClose?.()
    }
  }

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
        <p className="text-sm text-gray-500">Loading lists...</p>
      </div>
    )
  }

  if (lists.length === 0) {
    return (
      <>
        <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-8 text-center">
          <div className="mx-auto mb-3 text-gray-300">
            <FolderIcon className="h-8 w-8" />
          </div>
          <p className="text-sm text-gray-500">
            No lists created yet. Use the button above to create one.
          </p>
        </div>

        <ListModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          tagSuggestions={tagSuggestions}
          onCreate={onCreate}
        />
      </>
    )
  }

  return (
    <>
      <div className="rounded-lg border border-gray-200 divide-y divide-gray-200">
        {lists.map((list) => (
          <ListCard
            key={list.id}
            list={list}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />
        ))}
      </div>

      <ListModal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        list={editingList || undefined}
        tagSuggestions={tagSuggestions}
        onCreate={onCreate}
        onUpdate={onUpdate}
      />
    </>
  )
}
