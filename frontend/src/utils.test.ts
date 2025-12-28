import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  formatDate,
  formatRelativeDate,
  truncate,
  normalizeUrl,
  isValidUrl,
  getDomain,
  validateTag,
  normalizeTag,
  getFirstGroupTags,
  sortTags,
  TAG_PATTERN,
  addMonthsWithClamp,
  calculateArchivePresetDate,
} from './utils'
import type { ContentList, TagCount } from './types'

// ============================================================================
// Date Utilities
// ============================================================================

describe('formatDate', () => {
  it('should format ISO date string to readable format', () => {
    // Use midday UTC to avoid timezone edge cases
    expect(formatDate('2024-01-15T12:00:00Z')).toBe('Jan 15, 2024')
  })

  it('should handle different months', () => {
    // Use midday UTC to avoid timezone edge cases
    expect(formatDate('2024-06-15T12:00:00Z')).toBe('Jun 15, 2024')
    expect(formatDate('2024-12-25T12:00:00Z')).toBe('Dec 25, 2024')
  })

  it('should handle dates with different years', () => {
    // Use midday UTC to avoid timezone edge cases
    expect(formatDate('2020-03-10T12:00:00Z')).toBe('Mar 10, 2020')
    expect(formatDate('2025-11-30T12:00:00Z')).toBe('Nov 30, 2025')
  })
})

describe('formatRelativeDate', () => {
  beforeEach(() => {
    // Mock current time to 2024-06-15T12:00:00Z
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-06-15T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should return "just now" for very recent times', () => {
    expect(formatRelativeDate('2024-06-15T12:00:00Z')).toBe('just now')
  })

  it('should return minutes ago for past times within an hour', () => {
    expect(formatRelativeDate('2024-06-15T11:55:00Z')).toBe('5 minutes ago')
    expect(formatRelativeDate('2024-06-15T11:59:00Z')).toBe('1 minute ago')
    expect(formatRelativeDate('2024-06-15T11:30:00Z')).toBe('30 minutes ago')
  })

  it('should return hours ago for past times within a day', () => {
    expect(formatRelativeDate('2024-06-15T10:00:00Z')).toBe('2 hours ago')
    expect(formatRelativeDate('2024-06-15T11:00:00Z')).toBe('1 hour ago')
  })

  it('should return days ago for past times within 30 days', () => {
    expect(formatRelativeDate('2024-06-14T12:00:00Z')).toBe('1 day ago')
    expect(formatRelativeDate('2024-06-08T12:00:00Z')).toBe('7 days ago')
  })

  it('should return formatted date for past times over 30 days', () => {
    expect(formatRelativeDate('2024-05-01T12:00:00Z')).toBe('May 1, 2024')
  })

  it('should return "in X minutes" for near future times', () => {
    expect(formatRelativeDate('2024-06-15T12:05:00Z')).toBe('in 5 minutes')
    expect(formatRelativeDate('2024-06-15T12:30:00Z')).toBe('in 30 minutes')
  })

  it('should return "in X hours" for future times within a day', () => {
    expect(formatRelativeDate('2024-06-15T14:00:00Z')).toBe('in 2 hours')
  })

  it('should return "in X days" for future times within 30 days', () => {
    expect(formatRelativeDate('2024-06-16T12:00:00Z')).toBe('in 1 day')
    expect(formatRelativeDate('2024-06-22T12:00:00Z')).toBe('in 7 days')
  })

  it('should return formatted date for future times over 30 days', () => {
    expect(formatRelativeDate('2024-08-01T12:00:00Z')).toBe('Aug 1, 2024')
  })
})

// ============================================================================
// String Utilities
// ============================================================================

describe('truncate', () => {
  it('should return original text if shorter than max length', () => {
    expect(truncate('hello', 10)).toBe('hello')
  })

  it('should return original text if exactly max length', () => {
    expect(truncate('hello', 5)).toBe('hello')
  })

  it('should truncate text longer than max length with ellipsis', () => {
    expect(truncate('hello world', 5)).toBe('hello...')
  })

  it('should trim whitespace before adding ellipsis', () => {
    expect(truncate('hello   world', 8)).toBe('hello...')
  })

  it('should handle empty strings', () => {
    expect(truncate('', 10)).toBe('')
  })

  it('should handle max length of 0', () => {
    expect(truncate('hello', 0)).toBe('...')
  })
})

// ============================================================================
// URL Utilities
// ============================================================================

describe('normalizeUrl', () => {
  it('should add https:// to URL without protocol', () => {
    expect(normalizeUrl('example.com')).toBe('https://example.com')
    expect(normalizeUrl('www.example.com')).toBe('https://www.example.com')
  })

  it('should preserve existing https:// protocol', () => {
    expect(normalizeUrl('https://example.com')).toBe('https://example.com')
  })

  it('should preserve existing http:// protocol', () => {
    expect(normalizeUrl('http://example.com')).toBe('http://example.com')
  })

  it('should handle mixed case protocol', () => {
    expect(normalizeUrl('HTTPS://example.com')).toBe('HTTPS://example.com')
    expect(normalizeUrl('HTTP://example.com')).toBe('HTTP://example.com')
  })

  it('should trim whitespace', () => {
    expect(normalizeUrl('  example.com  ')).toBe('https://example.com')
  })

  it('should return empty string for empty input', () => {
    expect(normalizeUrl('')).toBe('')
    expect(normalizeUrl('   ')).toBe('')
  })
})

describe('isValidUrl', () => {
  it('should return true for valid https URLs', () => {
    expect(isValidUrl('https://example.com')).toBe(true)
    expect(isValidUrl('https://www.example.com/path')).toBe(true)
    expect(isValidUrl('https://example.com:8080')).toBe(true)
  })

  it('should return true for valid http URLs', () => {
    expect(isValidUrl('http://example.com')).toBe(true)
    expect(isValidUrl('http://localhost:3000')).toBe(true)
  })

  it('should return true for URLs without protocol (normalized)', () => {
    expect(isValidUrl('example.com')).toBe(true)
    expect(isValidUrl('www.example.com/path/to/page')).toBe(true)
  })

  it('should return false for invalid URLs', () => {
    expect(isValidUrl('')).toBe(false)
    expect(isValidUrl('not a url')).toBe(false)
    expect(isValidUrl('ftp://example.com')).toBe(false)
  })

  it('should return false for text with spaces', () => {
    expect(isValidUrl('asdfasfa asd asf')).toBe(false)
    expect(isValidUrl('hello world')).toBe(false)
    expect(isValidUrl('foo bar baz')).toBe(false)
  })

  it('should trim whitespace before validating', () => {
    expect(isValidUrl('  https://example.com  ')).toBe(true)
    expect(isValidUrl('\nhttps://example.com\n')).toBe(true)
    expect(isValidUrl('  example.com  ')).toBe(true)
  })
})

describe('getDomain', () => {
  it('should extract domain from URL', () => {
    expect(getDomain('https://example.com/path')).toBe('example.com')
  })

  it('should remove www prefix', () => {
    expect(getDomain('https://www.example.com')).toBe('example.com')
  })

  it('should handle subdomains', () => {
    expect(getDomain('https://blog.example.com')).toBe('blog.example.com')
  })

  it('should return original string for invalid URL', () => {
    expect(getDomain('not a url')).toBe('not a url')
  })

  it('should preserve port numbers', () => {
    expect(getDomain('https://example.com:8080')).toBe('example.com:8080')
  })
})

// ============================================================================
// Tag Utilities
// ============================================================================

describe('TAG_PATTERN', () => {
  it('should match valid simple tags', () => {
    expect(TAG_PATTERN.test('react')).toBe(true)
    expect(TAG_PATTERN.test('typescript')).toBe(true)
    expect(TAG_PATTERN.test('web3')).toBe(true)
  })

  it('should match tags with hyphens', () => {
    expect(TAG_PATTERN.test('react-native')).toBe(true)
    expect(TAG_PATTERN.test('node-js')).toBe(true)
    expect(TAG_PATTERN.test('machine-learning-ai')).toBe(true)
  })

  it('should match tags with numbers', () => {
    expect(TAG_PATTERN.test('es6')).toBe(true)
    expect(TAG_PATTERN.test('react18')).toBe(true)
  })

  it('should reject tags with uppercase', () => {
    expect(TAG_PATTERN.test('React')).toBe(false)
    expect(TAG_PATTERN.test('TYPESCRIPT')).toBe(false)
  })

  it('should reject tags with special characters', () => {
    expect(TAG_PATTERN.test('c++')).toBe(false)
    expect(TAG_PATTERN.test('c#')).toBe(false)
    expect(TAG_PATTERN.test('node.js')).toBe(false)
  })

  it('should reject tags with spaces or underscores', () => {
    expect(TAG_PATTERN.test('machine learning')).toBe(false)
    expect(TAG_PATTERN.test('machine_learning')).toBe(false)
  })

  it('should reject tags starting/ending with hyphens or consecutive hyphens', () => {
    expect(TAG_PATTERN.test('-react')).toBe(false)
    expect(TAG_PATTERN.test('react-')).toBe(false)
    expect(TAG_PATTERN.test('react--native')).toBe(false)
  })
})

describe('validateTag', () => {
  it('should return null for valid tags', () => {
    expect(validateTag('react')).toBeNull()
    expect(validateTag('react-native')).toBeNull()
    expect(validateTag('web3')).toBeNull()
  })

  it('should return null for uppercase tags (normalizes before validation)', () => {
    // validateTag normalizes to lowercase, so 'React' becomes 'react' which is valid
    expect(validateTag('React')).toBeNull()
    expect(validateTag('TYPESCRIPT')).toBeNull()
  })

  it('should return error for empty tags', () => {
    expect(validateTag('')).toBe('Tag cannot be empty')
    expect(validateTag('   ')).toBe('Tag cannot be empty')
  })

  it('should return error for tags with special characters', () => {
    expect(validateTag('c++')).toBe('Tags must be lowercase letters, numbers, and hyphens only')
    expect(validateTag('node.js')).toBe('Tags must be lowercase letters, numbers, and hyphens only')
    expect(validateTag('c#')).toBe('Tags must be lowercase letters, numbers, and hyphens only')
  })
})

describe('normalizeTag', () => {
  it('should convert to lowercase and trim', () => {
    expect(normalizeTag('REACT')).toBe('react')
    expect(normalizeTag('  react  ')).toBe('react')
    expect(normalizeTag('TypeScript')).toBe('typescript')
  })

  it('should handle already normalized tags', () => {
    expect(normalizeTag('react')).toBe('react')
    expect(normalizeTag('react-native')).toBe('react-native')
  })
})

// ============================================================================
// Filter Expression Utilities
// ============================================================================

describe('getFirstGroupTags', () => {
  const createList = (groups: { tags: string[] }[]): ContentList => ({
    id: 1,
    name: 'Test List',
    content_types: ['bookmark'],
    filter_expression: {
      groups: groups.map((g) => ({ tags: g.tags, operator: 'AND' as const })),
      group_operator: 'OR',
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    default_sort_by: null,
    default_sort_ascending: null,
  })

  it('should return tags from first group when list has single group', () => {
    const list = createList([{ tags: ['react', 'typescript'] }])
    expect(getFirstGroupTags(list)).toEqual(['react', 'typescript'])
  })

  it('should return only first group tags when list has multiple groups', () => {
    // Filter: (react AND typescript) OR (vue) OR (angular AND rxjs)
    const list = createList([
      { tags: ['react', 'typescript'] },
      { tags: ['vue'] },
      { tags: ['angular', 'rxjs'] },
    ])
    expect(getFirstGroupTags(list)).toEqual(['react', 'typescript'])
  })

  it('should return undefined when list is undefined', () => {
    expect(getFirstGroupTags(undefined)).toBeUndefined()
  })

  it('should return undefined when filter_expression is missing', () => {
    const list = { id: 1, name: 'Test', created_at: '', updated_at: '' } as ContentList
    expect(getFirstGroupTags(list)).toBeUndefined()
  })

  it('should return undefined when groups array is empty', () => {
    const list = createList([])
    expect(getFirstGroupTags(list)).toBeUndefined()
  })

  it('should return undefined when first group has no tags', () => {
    const list = createList([{ tags: [] }])
    expect(getFirstGroupTags(list)).toBeUndefined()
  })

  it('should return single tag when first group has one tag', () => {
    const list = createList([{ tags: ['javascript'] }])
    expect(getFirstGroupTags(list)).toEqual(['javascript'])
  })
})

// ============================================================================
// Sorting Utilities
// ============================================================================

describe('sortTags', () => {
  const tags: TagCount[] = [
    { name: 'react', count: 5 },
    { name: 'angular', count: 3 },
    { name: 'vue', count: 5 },
    { name: 'svelte', count: 1 },
  ]

  it('should sort by name ascending', () => {
    const sorted = sortTags(tags, 'name-asc')
    expect(sorted.map((t) => t.name)).toEqual(['angular', 'react', 'svelte', 'vue'])
  })

  it('should sort by name descending', () => {
    const sorted = sortTags(tags, 'name-desc')
    expect(sorted.map((t) => t.name)).toEqual(['vue', 'svelte', 'react', 'angular'])
  })

  it('should sort by count ascending with name as tiebreaker', () => {
    const sorted = sortTags(tags, 'count-asc')
    // svelte (1), angular (3), react (5), vue (5) - react before vue alphabetically
    expect(sorted.map((t) => t.name)).toEqual(['svelte', 'angular', 'react', 'vue'])
  })

  it('should sort by count descending with name as tiebreaker', () => {
    const sorted = sortTags(tags, 'count-desc')
    // react (5), vue (5), angular (3), svelte (1) - react before vue alphabetically
    expect(sorted.map((t) => t.name)).toEqual(['react', 'vue', 'angular', 'svelte'])
  })

  it('should not mutate original array', () => {
    const original = [...tags]
    sortTags(tags, 'name-asc')
    expect(tags).toEqual(original)
  })

  it('should handle empty array', () => {
    expect(sortTags([], 'name-asc')).toEqual([])
  })
})

// ============================================================================
// Archive Date Utilities
// ============================================================================

describe('addMonthsWithClamp', () => {
  it('should add months normally when no overflow occurs', () => {
    // Jan 15 + 1 month = Feb 15
    const jan15 = new Date(2025, 0, 15)
    const result = addMonthsWithClamp(jan15, 1)
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(1) // February
    expect(result.getDate()).toBe(15)
  })

  it('should clamp to last day of month when day overflows (Jan 31 + 1 month)', () => {
    // Jan 31 + 1 month should be Feb 28 (not Mar 3)
    const jan31 = new Date(2025, 0, 31)
    const result = addMonthsWithClamp(jan31, 1)
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(1) // February
    expect(result.getDate()).toBe(28) // Last day of Feb 2025
  })

  it('should handle leap year (Jan 31 + 1 month in leap year)', () => {
    // Jan 31 + 1 month in 2024 (leap year) = Feb 29
    const jan31 = new Date(2024, 0, 31)
    const result = addMonthsWithClamp(jan31, 1)
    expect(result.getFullYear()).toBe(2024)
    expect(result.getMonth()).toBe(1) // February
    expect(result.getDate()).toBe(29) // Leap year has Feb 29
  })

  it('should clamp when adding 6 months causes overflow (Aug 31 + 6 months)', () => {
    // Aug 31 + 6 months should be Feb 28 (not Mar 3)
    const aug31 = new Date(2025, 7, 31)
    const result = addMonthsWithClamp(aug31, 6)
    expect(result.getFullYear()).toBe(2026)
    expect(result.getMonth()).toBe(1) // February
    expect(result.getDate()).toBe(28)
  })

  it('should handle year boundary crossing (Oct 31 + 6 months)', () => {
    // Oct 31 + 6 months = Apr 30 (April has 30 days)
    const oct31 = new Date(2025, 9, 31)
    const result = addMonthsWithClamp(oct31, 6)
    expect(result.getFullYear()).toBe(2026)
    expect(result.getMonth()).toBe(3) // April
    expect(result.getDate()).toBe(30) // April has 30 days
  })

  it('should handle adding 12 months (1 year) with overflow', () => {
    // Feb 29, 2024 (leap year) + 12 months = Feb 28, 2025
    const feb29 = new Date(2024, 1, 29)
    const result = addMonthsWithClamp(feb29, 12)
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(1) // February
    expect(result.getDate()).toBe(28) // 2025 is not a leap year
  })

  it('should handle March 31 + 1 month (April has 30 days)', () => {
    // Mar 31 + 1 month = Apr 30
    const mar31 = new Date(2025, 2, 31)
    const result = addMonthsWithClamp(mar31, 1)
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(3) // April
    expect(result.getDate()).toBe(30)
  })

  it('should handle May 31 + 1 month (June has 30 days)', () => {
    // May 31 + 1 month = Jun 30
    const may31 = new Date(2025, 4, 31)
    const result = addMonthsWithClamp(may31, 1)
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(5) // June
    expect(result.getDate()).toBe(30)
  })

  it('should set time to 8:00 AM', () => {
    const jan15 = new Date(2025, 0, 15, 14, 30, 45) // 2:30:45 PM
    const result = addMonthsWithClamp(jan15, 1)
    expect(result.getHours()).toBe(8)
    expect(result.getMinutes()).toBe(0)
    expect(result.getSeconds()).toBe(0)
  })
})

describe('calculateArchivePresetDate', () => {
  // Use a fixed reference date for testing
  const referenceDate = new Date(2025, 0, 15, 10, 30, 0) // Jan 15, 2025 10:30 AM

  it('should return empty string for "none" preset', () => {
    expect(calculateArchivePresetDate('none', referenceDate)).toBe('')
  })

  it('should return empty string for "custom" preset', () => {
    expect(calculateArchivePresetDate('custom', referenceDate)).toBe('')
  })

  it('should calculate 1-week preset correctly', () => {
    const result = new Date(calculateArchivePresetDate('1-week', referenceDate))
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(0) // January
    expect(result.getDate()).toBe(22) // 15 + 7 = 22
    expect(result.getHours()).toBe(8)
  })

  it('should calculate 1-month preset correctly', () => {
    const result = new Date(calculateArchivePresetDate('1-month', referenceDate))
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(1) // February
    expect(result.getDate()).toBe(15)
  })

  it('should calculate end-of-month preset correctly', () => {
    const result = new Date(calculateArchivePresetDate('end-of-month', referenceDate))
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(0) // January
    expect(result.getDate()).toBe(31) // Last day of January
  })

  it('should calculate 6-months preset correctly', () => {
    const result = new Date(calculateArchivePresetDate('6-months', referenceDate))
    expect(result.getFullYear()).toBe(2025)
    expect(result.getMonth()).toBe(6) // July
    expect(result.getDate()).toBe(15)
  })

  it('should calculate 1-year preset correctly', () => {
    const result = new Date(calculateArchivePresetDate('1-year', referenceDate))
    expect(result.getFullYear()).toBe(2026)
    expect(result.getMonth()).toBe(0) // January
    expect(result.getDate()).toBe(15)
  })

  describe('overflow handling', () => {
    it('should handle Jan 31 + 1 month (Feb overflow)', () => {
      const jan31 = new Date(2025, 0, 31)
      const result = new Date(calculateArchivePresetDate('1-month', jan31))
      expect(result.getMonth()).toBe(1) // February
      expect(result.getDate()).toBe(28) // Clamped to last day
    })

    it('should handle Jan 31 + 6 months (July has 31 days, no overflow)', () => {
      const jan31 = new Date(2025, 0, 31)
      const result = new Date(calculateArchivePresetDate('6-months', jan31))
      expect(result.getMonth()).toBe(6) // July
      expect(result.getDate()).toBe(31) // July has 31 days
    })

    it('should handle Aug 31 + 6 months (Feb overflow)', () => {
      const aug31 = new Date(2025, 7, 31)
      const result = new Date(calculateArchivePresetDate('6-months', aug31))
      expect(result.getFullYear()).toBe(2026)
      expect(result.getMonth()).toBe(1) // February
      expect(result.getDate()).toBe(28) // Clamped to last day
    })

    it('should handle Feb 29 + 1 year (leap year to non-leap year)', () => {
      const feb29 = new Date(2024, 1, 29) // 2024 is a leap year
      const result = new Date(calculateArchivePresetDate('1-year', feb29))
      expect(result.getFullYear()).toBe(2025)
      expect(result.getMonth()).toBe(1) // February
      expect(result.getDate()).toBe(28) // 2025 is not a leap year
    })

    it('should handle Mar 31 + 1 month (April has 30 days)', () => {
      const mar31 = new Date(2025, 2, 31)
      const result = new Date(calculateArchivePresetDate('1-month', mar31))
      expect(result.getMonth()).toBe(3) // April
      expect(result.getDate()).toBe(30) // Clamped to last day of April
    })
  })

  it('should return valid ISO string', () => {
    const result = calculateArchivePresetDate('1-week', referenceDate)
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}Z$/)
  })
})
