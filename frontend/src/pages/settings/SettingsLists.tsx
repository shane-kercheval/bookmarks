/**
 * Settings page for Custom Lists and Tab Order management.
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
import { SectionTabOrderEditor } from '../../components/SectionTabOrderEditor'
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
 * Custom lists settings page - Lists and Tab Order.
 */
export function SettingsLists(): ReactNode {
  const { lists, isLoading: listsLoading, createList, updateList, deleteList } = useListsStore()
  const { computedSections, sectionOrder, isLoading: tabOrderLoading, fetchTabOrder } = useSettingsStore()
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
        <h1 className="text-2xl font-bold text-gray-900">List Settings</h1>
        <p className="mt-1 text-gray-500">
          Manage custom lists and customize sidebar order.
        </p>
      </div>

      {/* Custom Lists Section */}
      <Section
        title="Custom Lists"
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
        description="Customize the order of sections and items in the sidebar."
      >
        <SectionTabOrderEditor
          sections={computedSections}
          sectionOrder={sectionOrder}
          isLoading={tabOrderLoading}
        />
      </Section>
    </div>
  )
}
