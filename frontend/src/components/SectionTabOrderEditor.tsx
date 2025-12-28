/**
 * Section-aware tab order editor for reordering sidebar sections and items.
 * Supports reordering sections and reordering items within sections.
 */
import { useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import type { TabOrderSection, TabOrder, SectionName, TabOrderSections } from '../types'
import { ChevronUpIcon, ChevronDownIcon, FolderIcon, BookmarkIcon, NoteIcon } from './icons'
import { useSettingsStore } from '../stores/settingsStore'

interface SectionTabOrderEditorProps {
  sections: TabOrderSection[]
  sectionOrder: SectionName[]
  isLoading: boolean
}

/**
 * Get icon for item type.
 */
function getItemIcon(type: 'builtin' | 'list', sectionName: SectionName): ReactNode {
  if (type === 'list') {
    return <FolderIcon className="h-4 w-4" />
  }
  // Builtin icons based on section
  if (sectionName === 'notes') {
    return <NoteIcon className="h-4 w-4" />
  }
  return <BookmarkIcon className="h-4 w-4" />
}

/**
 * Section header color classes.
 */
const SECTION_COLORS: Record<SectionName, string> = {
  shared: 'text-purple-600',
  bookmarks: 'text-blue-600',
  notes: 'text-amber-600',
}

/**
 * Section-aware tab order editor with section and item reordering.
 */
export function SectionTabOrderEditor({
  sections,
  sectionOrder,
  isLoading,
}: SectionTabOrderEditorProps): ReactNode {
  const updateTabOrder = useSettingsStore((state) => state.updateTabOrder)

  // Local state for editing
  const [localSectionOrder, setLocalSectionOrder] = useState<SectionName[]>([])
  const [localSectionItems, setLocalSectionItems] = useState<Record<SectionName, string[]>>({
    shared: [],
    bookmarks: [],
    notes: [],
  })
  const [hasChanges, setHasChanges] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  // Sync local state with props
  useEffect(() => {
    setLocalSectionOrder(sectionOrder)
    const items: Record<SectionName, string[]> = {
      shared: [],
      bookmarks: [],
      notes: [],
    }
    sections.forEach((section) => {
      items[section.name] = section.items.map((item) => item.key)
    })
    setLocalSectionItems(items)
    setHasChanges(false)
  }, [sections, sectionOrder])

  // Get section data by name
  const getSectionByName = (name: SectionName): TabOrderSection | undefined => {
    return sections.find((s) => s.name === name)
  }

  // Move a section up or down
  const moveSection = (index: number, direction: 'up' | 'down'): void => {
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= localSectionOrder.length) return

    const newOrder = [...localSectionOrder]
    const [removed] = newOrder.splice(index, 1)
    newOrder.splice(newIndex, 0, removed)
    setLocalSectionOrder(newOrder)
    setHasChanges(true)
  }

  // Move an item within a section
  const moveItem = (sectionName: SectionName, index: number, direction: 'up' | 'down'): void => {
    const items = localSectionItems[sectionName]
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= items.length) return

    const newItems = [...items]
    const [removed] = newItems.splice(index, 1)
    newItems.splice(newIndex, 0, removed)
    setLocalSectionItems((prev) => ({
      ...prev,
      [sectionName]: newItems,
    }))
    setHasChanges(true)
  }

  // Save changes
  const handleSave = async (): Promise<void> => {
    setIsSaving(true)
    try {
      const tabOrder: TabOrder = {
        sections: localSectionItems as TabOrderSections,
        section_order: localSectionOrder,
      }
      await updateTabOrder(tabOrder)
      setHasChanges(false)
    } catch {
      toast.error('Failed to save sidebar order')
    } finally {
      setIsSaving(false)
    }
  }

  // Reset changes
  const handleReset = (): void => {
    setLocalSectionOrder(sectionOrder)
    const items: Record<SectionName, string[]> = {
      shared: [],
      bookmarks: [],
      notes: [],
    }
    sections.forEach((section) => {
      items[section.name] = section.items.map((item) => item.key)
    })
    setLocalSectionItems(items)
    setHasChanges(false)
  }

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
        <p className="text-sm text-gray-500">Loading sidebar order...</p>
      </div>
    )
  }

  if (sections.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
        <p className="text-sm text-gray-500">Using default sidebar order.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Section list */}
      <div className="space-y-4">
        {localSectionOrder.map((sectionName, sectionIndex) => {
          const section = getSectionByName(sectionName)
          if (!section) return null

          const items = localSectionItems[sectionName]
          const sectionData = sections.find((s) => s.name === sectionName)

          return (
            <div key={sectionName} className="rounded-lg border border-gray-200 overflow-hidden">
              {/* Section header */}
              <div className="flex items-center gap-3 p-3 bg-gray-50 border-b border-gray-200">
                {/* Section label */}
                <span className={`font-semibold text-sm uppercase tracking-wide flex-1 ${SECTION_COLORS[sectionName]}`}>
                  {section.label}
                </span>

                {/* Section reorder buttons */}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => moveSection(sectionIndex, 'up')}
                    disabled={sectionIndex === 0}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    title="Move section up"
                  >
                    <ChevronUpIcon />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveSection(sectionIndex, 'down')}
                    disabled={sectionIndex === localSectionOrder.length - 1}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    title="Move section down"
                  >
                    <ChevronDownIcon />
                  </button>
                </div>
              </div>

              {/* Section items */}
              {items.length > 0 ? (
                <div className="divide-y divide-gray-100">
                  {items.map((itemKey, itemIndex) => {
                    const itemData = sectionData?.items.find((i) => i.key === itemKey)
                    if (!itemData) return null

                    return (
                      <div
                        key={itemKey}
                        className="flex items-center gap-3 p-3 pl-8 list-item-hover"
                      >
                        {/* Item info */}
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <span className="text-gray-400">
                            {getItemIcon(itemData.type, sectionName)}
                          </span>
                          <span className="font-medium text-gray-900 truncate">
                            {itemData.label}
                          </span>
                          {itemData.type === 'builtin' && (
                            <span className="text-xs text-gray-400 shrink-0">(built-in)</span>
                          )}
                        </div>

                        {/* Item reorder buttons */}
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => moveItem(sectionName, itemIndex, 'up')}
                            disabled={itemIndex === 0}
                            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                            title="Move item up"
                          >
                            <ChevronUpIcon />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveItem(sectionName, itemIndex, 'down')}
                            disabled={itemIndex === items.length - 1}
                            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                            title="Move item down"
                          >
                            <ChevronDownIcon />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="p-3 pl-8 text-sm text-gray-400 italic">
                  No items in this section
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Save/Reset buttons */}
      {hasChanges && (
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleReset}
            className="btn-secondary"
            disabled={isSaving}
          >
            Reset
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="btn-primary"
            disabled={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save Order'}
          </button>
        </div>
      )}

      <p className="text-xs text-gray-400">
        Use the arrows to reorder sections and items. Changes are saved when you click "Save Order".
      </p>
    </div>
  )
}
