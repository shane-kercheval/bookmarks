/**
 * Settings page for Bookmark Lists and Tab Order management.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { PlusIcon } from '../../components/icons'
import { useListsStore } from '../../stores/listsStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useTagsStore } from '../../stores/tagsStore'
import { useUIPreferencesStore } from '../../stores/uiPreferencesStore'
import { ListManager } from '../../components/ListManager'
import type { ContentListCreate, ContentListUpdate, ContentList } from '../../types'

/**
 * Section wrapper component for consistent styling.
 */
interface SectionProps {
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
}

function Section({ title, description, action, children }: SectionProps): ReactNode {
  return (
    <section className="mb-8">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
          {description && (
            <p className="mt-1 text-sm text-gray-500">{description}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

/**
 * Bookmark settings page - Lists and Tab Order.
 */
export function SettingsBookmarks(): ReactNode {
  const { lists, isLoading: listsLoading, createList, updateList, deleteList } = useListsStore()
  const { fetchTabOrder } = useSettingsStore()
  const tags = useTagsStore((state) => state.tags)
  const { sortOverrides, clearAllSortOverrides } = useUIPreferencesStore()
  const hasSortOverrides = Object.keys(sortOverrides).length > 0
  const [showCreateListModal, setShowCreateListModal] = useState(false)

  // List handlers
  const handleCreateList = async (data: ContentListCreate): Promise<ContentList> => {
    try {
      const response = await createList(data)
      // Refresh tab order since new list was added
      fetchTabOrder()
      return response
    } catch {
      toast.error('Failed to create list')
      throw new Error('Failed to create list')
    }
  }

  const handleUpdateList = async (id: number, data: ContentListUpdate): Promise<ContentList> => {
    try {
      const response = await updateList(id, data)
      // Refresh tab order in case name changed
      fetchTabOrder()
      return response
    } catch {
      toast.error('Failed to update list')
      throw new Error('Failed to update list')
    }
  }

  const handleDeleteList = async (id: number): Promise<void> => {
    try {
      await deleteList(id)
      // Refresh tab order since list was removed
      fetchTabOrder()
    } catch {
      toast.error('Failed to delete list')
      throw new Error('Failed to delete list')
    }
  }

  // Sort override handlers
  const handleResetSortOrders = (): void => {
    clearAllSortOverrides()
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Bookmark Settings</h1>
        <p className="mt-1 text-gray-500">
          Manage bookmark lists and customize sidebar order.
        </p>
      </div>

      {/* Bookmark Lists Section */}
      <Section
        title="Bookmark Lists"
        description="Create custom lists based on tag filters. Lists appear in the sidebar."
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={handleResetSortOrders}
              disabled={!hasSortOverrides}
              className="btn-secondary text-sm"
              title={hasSortOverrides ? `${Object.keys(sortOverrides).length} cached sort order${Object.keys(sortOverrides).length !== 1 ? 's' : ''}` : 'No cached sort orders'}
            >
              Reset Cached Sort Orders
            </button>
            <button
              onClick={() => setShowCreateListModal(true)}
              className="btn-primary p-2"
              title="Create List"
            >
              <PlusIcon />
            </button>
          </div>
        }
      >
        <ListManager
          lists={lists}
          isLoading={listsLoading}
          tagSuggestions={tags}
          onCreate={handleCreateList}
          onUpdate={handleUpdateList}
          onDelete={handleDeleteList}
          isCreateModalOpen={showCreateListModal}
          onCreateModalClose={() => setShowCreateListModal(false)}
        />
      </Section>

      {/* Tab Order Section - temporarily disabled pending section-based editor (M13) */}
      <Section
        title="Sidebar Order"
        description="View the current sidebar navigation order."
      >
        <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
          <p className="text-sm text-gray-600">
            The sidebar now uses section-based navigation (Shared, Bookmarks, Notes).
            Section and item reordering will be available in a future update.
          </p>
        </div>
      </Section>
    </div>
  )
}
