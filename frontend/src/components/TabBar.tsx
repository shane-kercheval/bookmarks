/**
 * Reusable tab bar component for horizontal navigation.
 *
 * A pure presentational component that renders tabs with active state styling.
 * Has no knowledge of specific domains (bookmarks, settings, etc.).
 */
import type { ReactNode } from 'react'

export interface Tab {
  key: string
  label: string
}

export interface TabBarProps {
  /** Array of tabs to display */
  tabs: Tab[]
  /** Key of the currently active tab */
  activeTabKey: string
  /** Called when a tab is clicked */
  onTabChange: (key: string) => void
  /** Optional fallback tabs to show when main tabs array is empty (e.g., while loading) */
  fallbackTabs?: Tab[]
}

/**
 * Horizontal tab navigation bar.
 *
 * Usage:
 * ```tsx
 * <TabBar
 *   tabs={[
 *     { key: 'all', label: 'All Items' },
 *     { key: 'archived', label: 'Archived' },
 *   ]}
 *   activeTabKey={currentTab}
 *   onTabChange={setCurrentTab}
 * />
 * ```
 */
export function TabBar({ tabs, activeTabKey, onTabChange, fallbackTabs }: TabBarProps): ReactNode {
  const displayTabs = tabs.length > 0 ? tabs : fallbackTabs || []

  return (
    <div className="mb-4 border-b border-gray-200">
      <nav className="-mb-px flex gap-4 overflow-x-auto" aria-label="Tabs">
        {displayTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTabKey === tab.key
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
