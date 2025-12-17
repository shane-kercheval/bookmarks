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
  TAG_PATTERN,
} from './utils'

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
