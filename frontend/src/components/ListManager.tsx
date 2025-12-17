/**
 * List manager component for displaying and managing bookmark lists.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { BookmarkList, BookmarkListCreate, BookmarkListUpdate, TagCount } from '../types'
import { ListCard } from './ListCard'
import { ListModal } from './ListModal'
import { PlusIcon, FolderIcon } from './icons'

interface ListManagerProps {
  lists: BookmarkList[]
  isLoading: boolean
  tagSuggestions: TagCount[]
  onCreate: (data: BookmarkListCreate) => Promise<BookmarkList>
  onUpdate: (id: number, data: BookmarkListUpdate) => Promise<BookmarkList>
  onDelete: (id: number) => Promise<void>
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
}: ListManagerProps): ReactNode {
  const [showModal, setShowModal] = useState(false)
  const [editingList, setEditingList] = useState<BookmarkList | null>(null)

  const handleEdit = (list: BookmarkList): void => {
    setEditingList(list)
    setShowModal(true)
  }

  const handleDelete = async (list: BookmarkList): Promise<void> => {
    await onDelete(list.id)
  }

  const handleCloseModal = (): void => {
    setShowModal(false)
    setEditingList(null)
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
          <p className="text-sm text-gray-500 mb-4">
            No lists created yet. Create a list to organize your bookmarks.
          </p>
          <button
            onClick={() => setShowModal(true)}
            className="btn-primary inline-flex items-center gap-2"
          >
            <PlusIcon />
            Create List
          </button>
        </div>

        <ListModal
          isOpen={showModal}
          onClose={handleCloseModal}
          tagSuggestions={tagSuggestions}
          onCreate={onCreate}
        />
      </>
    )
  }

  return (
    <>
      <div className="space-y-3">
        <div className="flex justify-end">
          <button
            onClick={() => setShowModal(true)}
            className="btn-primary inline-flex items-center gap-2"
          >
            <PlusIcon />
            Create List
          </button>
        </div>

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
      </div>

      <ListModal
        isOpen={showModal}
        onClose={handleCloseModal}
        list={editingList || undefined}
        tagSuggestions={tagSuggestions}
        onCreate={onCreate}
        onUpdate={onUpdate}
      />
    </>
  )
}
