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
import { TabOrderEditor } from '../../components/TabOrderEditor'
import type { BookmarkListCreate, BookmarkListUpdate, BookmarkList } from '../../types'

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
  const { computedTabOrder, isLoading: settingsLoading, fetchTabOrder, updateSettings } = useSettingsStore()
  const tags = useTagsStore((state) => state.tags)
  const { sortOverrides, clearAllSortOverrides } = useUIPreferencesStore()
  const hasSortOverrides = Object.keys(sortOverrides).length > 0
  const [showCreateListModal, setShowCreateListModal] = useState(false)

  // List handlers
  const handleCreateList = async (data: BookmarkListCreate): Promise<BookmarkList> => {
    try {
      const response = await createList(data)
      // Refresh tab order since new list was added
      fetchTabOrder()
      toast.success(`List "${data.name}" created`)
      return response
    } catch {
      toast.error('Failed to create list')
      throw new Error('Failed to create list')
    }
  }

  const handleUpdateList = async (id: number, data: BookmarkListUpdate): Promise<BookmarkList> => {
    try {
      const response = await updateList(id, data)
      // Refresh tab order in case name changed
      fetchTabOrder()
      toast.success('List updated')
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
      toast.success('List deleted')
    } catch {
      toast.error('Failed to delete list')
      throw new Error('Failed to delete list')
    }
  }

  // Tab order handlers
  const handleSaveTabOrder = async (tabOrder: string[]): Promise<void> => {
    try {
      await updateSettings({ tab_order: tabOrder })
      // Refresh to get the updated computed tab order
      fetchTabOrder()
      toast.success('Tab order saved')
    } catch {
      toast.error('Failed to save tab order')
      throw new Error('Failed to save tab order')
    }
  }

  // Sort override handlers
  const handleResetSortOrders = (): void => {
    clearAllSortOverrides()
    toast.success('All sort orders reset to defaults')
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

      {/* Tab Order Section */}
      <Section
        title="Sidebar Order"
        description="Customize the order of items in the sidebar."
      >
        <TabOrderEditor
          items={computedTabOrder}
          isLoading={settingsLoading}
          onSave={handleSaveTabOrder}
        />
      </Section>
    </div>
  )
}
