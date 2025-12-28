/**
 * Main sidebar component with navigation and user info.
 */
import type { ReactNode } from 'react'
import { useSidebarStore } from '../../stores/sidebarStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { getTabRoute } from './routes'
import { SidebarSection } from './SidebarSection'
import { SidebarNavItem } from './SidebarNavItem'
import { SidebarUserSection } from './SidebarUserSection'
import {
  SidebarBookmarkIcon,
  SidebarNoteIcon,
  SharedIcon,
  SettingsIcon,
  CollapseIcon,
  MenuIcon,
  CloseIcon,
} from '../icons'
import type { SectionName } from '../../types'

function getSectionIcon(sectionName: SectionName): ReactNode {
  switch (sectionName) {
    case 'shared':
      return <SharedIcon className="h-5 w-5 text-purple-600" />
    case 'bookmarks':
      return <SidebarBookmarkIcon className="h-5 w-5 text-blue-600" />
    case 'notes':
      return <SidebarNoteIcon className="h-5 w-5 text-amber-600" />
  }
}

function getSectionVariant(sectionName: SectionName): 'blue' | 'amber' | 'purple' {
  switch (sectionName) {
    case 'shared':
      return 'purple'
    case 'bookmarks':
      return 'blue'
    case 'notes':
      return 'amber'
  }
}

interface SidebarContentProps {
  isCollapsed: boolean
  onNavClick?: () => void
}

function SidebarContent({ isCollapsed, onNavClick }: SidebarContentProps): ReactNode {
  const { expandedSections, toggleSection, toggleCollapse } = useSidebarStore()
  const computedSections = useSettingsStore((state) => state.computedSections)
  const sectionOrder = useSettingsStore((state) => state.sectionOrder)

  const isSettingsExpanded = expandedSections.includes('settings')

  // Build ordered sections from computed data
  const orderedSections = sectionOrder
    .map((name) => computedSections.find((s) => s.name === name))
    .filter((s): s is NonNullable<typeof s> => s !== undefined)

  return (
    <div className="flex h-full flex-col">
      {/* Navigation Sections */}
      <nav className="flex-1 space-y-1 px-2">
        {orderedSections.map((section) => {
          const isExpanded = expandedSections.includes(section.name)
          const variant = getSectionVariant(section.name)

          return (
            <SidebarSection
              key={section.name}
              title={section.label}
              icon={getSectionIcon(section.name)}
              isExpanded={isExpanded}
              onToggle={() => toggleSection(section.name)}
              isCollapsed={isCollapsed}
              collapsible={section.collapsible}
            >
              {section.items.map((item) => (
                <SidebarNavItem
                  key={item.key}
                  to={getTabRoute(item.key, section.name)}
                  label={item.label}
                  isCollapsed={isCollapsed}
                  onClick={onNavClick}
                  variant={variant}
                />
              ))}
            </SidebarSection>
          )
        })}

        <SidebarSection
          title="Settings"
          icon={<SettingsIcon className="h-5 w-5" />}
          isExpanded={isSettingsExpanded}
          onToggle={() => toggleSection('settings')}
          isCollapsed={isCollapsed}
          collapsible={true}
        >
          <SidebarNavItem
            to="/app/settings/general"
            label="General"
            isCollapsed={isCollapsed}
            onClick={onNavClick}
          />
          <SidebarNavItem
            to="/app/settings/lists"
            label="Lists"
            isCollapsed={isCollapsed}
            onClick={onNavClick}
          />
          <SidebarNavItem
            to="/app/settings/tags"
            label="Tags"
            isCollapsed={isCollapsed}
            onClick={onNavClick}
          />
          <SidebarNavItem
            to="/app/settings/tokens"
            label="Personal Access Tokens"
            isCollapsed={isCollapsed}
            onClick={onNavClick}
          />
          <SidebarNavItem
            to="/app/settings/mcp"
            label="MCP Integration"
            isCollapsed={isCollapsed}
            onClick={onNavClick}
          />
        </SidebarSection>
      </nav>

      {/* Collapse Toggle (desktop only) */}
      <div className="hidden border-t border-gray-200 px-2 py-2 md:block">
        <button
          onClick={toggleCollapse}
          className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700 ${
            isCollapsed ? 'justify-center' : ''
          }`}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <CollapseIcon className={`h-4 w-4 transition-transform ${isCollapsed ? 'rotate-180' : ''}`} />
          {!isCollapsed && <span>Collapse</span>}
        </button>
      </div>

      {/* User Section */}
      <div className="border-t border-gray-200 px-2 py-3">
        <SidebarUserSection isCollapsed={isCollapsed} />
      </div>
    </div>
  )
}

export function Sidebar(): ReactNode {
  const { isCollapsed, isMobileOpen, toggleMobile, closeMobile } = useSidebarStore()

  return (
    <>
      {/* Mobile menu button */}
      <button
        onClick={toggleMobile}
        className="fixed left-4 top-4 z-50 rounded-lg bg-white p-2 shadow-md md:hidden"
        aria-label={isMobileOpen ? 'Close menu' : 'Open menu'}
      >
        {isMobileOpen ? <CloseIcon /> : <MenuIcon />}
      </button>

      {/* Mobile backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-gray-900/20 backdrop-blur-sm md:hidden"
          onClick={closeMobile}
        />
      )}

      {/* Mobile sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-white shadow-lg transition-transform md:hidden ${
          isMobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="h-full pt-16">
          <SidebarContent isCollapsed={false} onNavClick={closeMobile} />
        </div>
      </aside>

      {/* Desktop sidebar */}
      <aside
        className={`hidden h-screen flex-shrink-0 border-r border-gray-200 bg-white transition-all md:block ${
          isCollapsed ? 'w-16' : 'w-64'
        }`}
      >
        <div className="h-full py-4">
          <SidebarContent isCollapsed={isCollapsed} />
        </div>
      </aside>
    </>
  )
}
