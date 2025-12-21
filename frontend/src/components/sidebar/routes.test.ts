/**
 * Tests for Sidebar route generation.
 *
 * These tests ensure navigation links use the correct /app prefix.
 * This prevents bugs where clicking sidebar items doesn't navigate correctly.
 */
import { describe, it, expect } from 'vitest'
import { getTabRoute } from './routes'

describe('getTabRoute', () => {
  it('returns /app/bookmarks for "all"', () => {
    expect(getTabRoute('all')).toBe('/app/bookmarks')
  })

  it('returns /app/bookmarks/archived for "archived"', () => {
    expect(getTabRoute('archived')).toBe('/app/bookmarks/archived')
  })

  it('returns /app/bookmarks/trash for "trash"', () => {
    expect(getTabRoute('trash')).toBe('/app/bookmarks/trash')
  })

  it('returns /app/bookmarks/lists/:id for list keys', () => {
    expect(getTabRoute('list:123')).toBe('/app/bookmarks/lists/123')
    expect(getTabRoute('list:456')).toBe('/app/bookmarks/lists/456')
  })

  it('returns /app/bookmarks for unknown keys', () => {
    expect(getTabRoute('unknown')).toBe('/app/bookmarks')
    expect(getTabRoute('')).toBe('/app/bookmarks')
  })

  // Guard against regression: all routes must start with /app
  it('all routes start with /app', () => {
    const testKeys = ['all', 'archived', 'trash', 'list:1', 'unknown', '']
    for (const key of testKeys) {
      const route = getTabRoute(key)
      expect(route.startsWith('/app/')).toBe(true)
    }
  })
})
