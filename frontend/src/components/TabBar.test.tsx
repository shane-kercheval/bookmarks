/**
 * Tests for TabBar component.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TabBar, type Tab } from './TabBar'

describe('TabBar', () => {
  const defaultTabs: Tab[] = [
    { key: 'all', label: 'All Items' },
    { key: 'archived', label: 'Archived' },
    { key: 'trash', label: 'Trash' },
  ]

  it('renders all provided tabs', () => {
    render(
      <TabBar
        tabs={defaultTabs}
        activeTabKey="all"
        onTabChange={vi.fn()}
      />
    )

    expect(screen.getByText('All Items')).toBeInTheDocument()
    expect(screen.getByText('Archived')).toBeInTheDocument()
    expect(screen.getByText('Trash')).toBeInTheDocument()
  })

  it('applies active styling to the current tab', () => {
    render(
      <TabBar
        tabs={defaultTabs}
        activeTabKey="archived"
        onTabChange={vi.fn()}
      />
    )

    const archivedTab = screen.getByText('Archived')
    const allTab = screen.getByText('All Items')

    // Active tab should have gray-900 text color
    expect(archivedTab).toHaveClass('text-gray-900')
    expect(archivedTab).toHaveClass('border-gray-900')

    // Inactive tab should have gray-500 text color
    expect(allTab).toHaveClass('text-gray-500')
    expect(allTab).toHaveClass('border-transparent')
  })

  it('calls onTabChange with correct key when tab is clicked', () => {
    const onTabChange = vi.fn()

    render(
      <TabBar
        tabs={defaultTabs}
        activeTabKey="all"
        onTabChange={onTabChange}
      />
    )

    fireEvent.click(screen.getByText('Archived'))

    expect(onTabChange).toHaveBeenCalledTimes(1)
    expect(onTabChange).toHaveBeenCalledWith('archived')
  })

  it('calls onTabChange when clicking the active tab', () => {
    const onTabChange = vi.fn()

    render(
      <TabBar
        tabs={defaultTabs}
        activeTabKey="all"
        onTabChange={onTabChange}
      />
    )

    fireEvent.click(screen.getByText('All Items'))

    expect(onTabChange).toHaveBeenCalledWith('all')
  })

  it('renders fallbackTabs when tabs array is empty', () => {
    const fallbackTabs: Tab[] = [
      { key: 'default1', label: 'Default Tab 1' },
      { key: 'default2', label: 'Default Tab 2' },
    ]

    render(
      <TabBar
        tabs={[]}
        activeTabKey="default1"
        onTabChange={vi.fn()}
        fallbackTabs={fallbackTabs}
      />
    )

    expect(screen.getByText('Default Tab 1')).toBeInTheDocument()
    expect(screen.getByText('Default Tab 2')).toBeInTheDocument()
  })

  it('prefers tabs over fallbackTabs when both provided', () => {
    const fallbackTabs: Tab[] = [
      { key: 'fallback', label: 'Fallback Tab' },
    ]

    render(
      <TabBar
        tabs={defaultTabs}
        activeTabKey="all"
        onTabChange={vi.fn()}
        fallbackTabs={fallbackTabs}
      />
    )

    expect(screen.getByText('All Items')).toBeInTheDocument()
    expect(screen.queryByText('Fallback Tab')).not.toBeInTheDocument()
  })

  it('renders nothing when tabs and fallbackTabs are both empty', () => {
    const { container } = render(
      <TabBar
        tabs={[]}
        activeTabKey="none"
        onTabChange={vi.fn()}
      />
    )

    const nav = container.querySelector('nav')
    expect(nav?.children).toHaveLength(0)
  })

  it('handles tabs with special characters in labels', () => {
    const specialTabs: Tab[] = [
      { key: 'list:1', label: 'My List (5)' },
      { key: 'list:2', label: 'Work & Projects' },
    ]

    render(
      <TabBar
        tabs={specialTabs}
        activeTabKey="list:1"
        onTabChange={vi.fn()}
      />
    )

    expect(screen.getByText('My List (5)')).toBeInTheDocument()
    expect(screen.getByText('Work & Projects')).toBeInTheDocument()
  })

  it('has accessible navigation landmark', () => {
    render(
      <TabBar
        tabs={defaultTabs}
        activeTabKey="all"
        onTabChange={vi.fn()}
      />
    )

    expect(screen.getByRole('navigation', { name: 'Tabs' })).toBeInTheDocument()
  })
})
