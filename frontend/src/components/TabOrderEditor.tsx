/**
 * Tab order editor component for reordering tabs.
 * Uses up/down buttons for simple reordering without drag-and-drop library.
 */
import { useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import type { TabOrderItem } from '../types'
import { ChevronUpIcon, ChevronDownIcon, GripIcon, FolderIcon, BookmarkIcon } from './icons'

interface TabOrderEditorProps {
  items: TabOrderItem[]
  isLoading: boolean
  onSave: (tabOrder: string[]) => Promise<void>
}

/**
 * Get icon for tab type.
 */
function getTabIcon(type: 'builtin' | 'list'): ReactNode {
  if (type === 'list') {
    return <FolderIcon className="h-4 w-4" />
  }
  // Builtin icon (bookmark)
  return <BookmarkIcon className="h-4 w-4" />
}

/**
 * Tab order editor with up/down reordering.
 */
export function TabOrderEditor({ items, isLoading, onSave }: TabOrderEditorProps): ReactNode {
  const [localItems, setLocalItems] = useState<TabOrderItem[]>([])
  const [hasChanges, setHasChanges] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  // Sync local state with props
  useEffect(() => {
    setLocalItems(items)
    setHasChanges(false)
  }, [items])

  const moveItem = (index: number, direction: 'up' | 'down'): void => {
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= localItems.length) return

    const newItems = [...localItems]
    const [removed] = newItems.splice(index, 1)
    newItems.splice(newIndex, 0, removed)
    setLocalItems(newItems)
    setHasChanges(true)
  }

  const handleSave = async (): Promise<void> => {
    setIsSaving(true)
    try {
      const tabOrder = localItems.map((item) => item.key)
      await onSave(tabOrder)
      setHasChanges(false)
    } finally {
      setIsSaving(false)
    }
  }

  const handleReset = (): void => {
    setLocalItems(items)
    setHasChanges(false)
  }

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
        <p className="text-sm text-gray-500">Loading tab order...</p>
      </div>
    )
  }

  if (localItems.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
        <p className="text-sm text-gray-500">Using default tab order.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-gray-200 divide-y divide-gray-200">
        {localItems.map((item, index) => (
          <div
            key={item.key}
            className="flex items-center gap-3 p-3 list-item-hover"
          >
            {/* Grip icon (decorative) */}
            <span className="text-gray-300">
              <GripIcon />
            </span>

            {/* Tab info */}
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="text-gray-400">
                {getTabIcon(item.type)}
              </span>
              <span className="font-medium text-gray-900 truncate">{item.label}</span>
              {item.type === 'builtin' && (
                <span className="text-xs text-gray-400 shrink-0">(built-in)</span>
              )}
            </div>

            {/* Reorder buttons */}
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => moveItem(index, 'up')}
                disabled={index === 0}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                title="Move up"
              >
                <ChevronUpIcon />
              </button>
              <button
                type="button"
                onClick={() => moveItem(index, 'down')}
                disabled={index === localItems.length - 1}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                title="Move down"
              >
                <ChevronDownIcon />
              </button>
            </div>
          </div>
        ))}
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
        Use the arrows to reorder tabs. Changes are saved when you click "Save Order".
      </p>
    </div>
  )
}
