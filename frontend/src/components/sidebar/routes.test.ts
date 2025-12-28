/**
 * Tests for Sidebar route generation.
 *
 * These tests ensure navigation links use the correct /app prefix.
 * This prevents bugs where clicking sidebar items doesn't navigate correctly.
 */
import { describe, it, expect } from 'vitest'
import { getTabRoute } from './routes'

describe('getTabRoute', () => {
  describe('shared section', () => {
    it('returns /app/content for "all"', () => {
      expect(getTabRoute('all', 'shared')).toBe('/app/content')
    })

    it('returns /app/content/archived for "archived"', () => {
      expect(getTabRoute('archived', 'shared')).toBe('/app/content/archived')
    })

    it('returns /app/content/trash for "trash"', () => {
      expect(getTabRoute('trash', 'shared')).toBe('/app/content/trash')
    })

    it('returns /app/content/lists/:id for shared list keys', () => {
      expect(getTabRoute('list:123', 'shared')).toBe('/app/content/lists/123')
    })
  })

  describe('bookmarks section', () => {
    it('returns /app/bookmarks for "all-bookmarks"', () => {
      expect(getTabRoute('all-bookmarks', 'bookmarks')).toBe('/app/bookmarks')
    })

    it('returns /app/bookmarks/lists/:id for bookmark list keys', () => {
      expect(getTabRoute('list:456', 'bookmarks')).toBe('/app/bookmarks/lists/456')
    })
  })

  describe('notes section', () => {
    it('returns /app/notes for "all-notes"', () => {
      expect(getTabRoute('all-notes', 'notes')).toBe('/app/notes')
    })

    it('returns /app/notes/lists/:id for note list keys', () => {
      expect(getTabRoute('list:789', 'notes')).toBe('/app/notes/lists/789')
    })
  })

  describe('fallback behavior', () => {
    it('returns /app/bookmarks for unknown keys', () => {
      expect(getTabRoute('unknown', 'shared')).toBe('/app/bookmarks')
      expect(getTabRoute('', 'bookmarks')).toBe('/app/bookmarks')
    })
  })

  // Guard against regression: all routes must start with /app
  it('all routes start with /app', () => {
    const testCases: Array<{ key: string; section: 'shared' | 'bookmarks' | 'notes' }> = [
      { key: 'all', section: 'shared' },
      { key: 'archived', section: 'shared' },
      { key: 'trash', section: 'shared' },
      { key: 'all-bookmarks', section: 'bookmarks' },
      { key: 'all-notes', section: 'notes' },
      { key: 'list:1', section: 'shared' },
      { key: 'list:2', section: 'bookmarks' },
      { key: 'list:3', section: 'notes' },
      { key: 'unknown', section: 'shared' },
    ]
    for (const { key, section } of testCases) {
      const route = getTabRoute(key, section)
      expect(route.startsWith('/app/')).toBe(true)
    }
  })
})
