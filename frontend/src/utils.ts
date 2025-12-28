/**
 * Utility functions for the bookmarks application.
 */

// ============================================================================
// Date Utilities
// ============================================================================

/**
 * Format a date string to a readable format.
 * @param dateString - ISO date string
 * @returns Formatted date like "Jan 15, 2024"
 */
export function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/**
 * Format a date string to a relative time (e.g., "2 days ago", "in 3 hours").
 * @param dateString - ISO date string
 * @returns Relative time string
 */
export function formatRelativeDate(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = date.getTime() - now.getTime()
  const diffSecs = Math.round(diffMs / 1000)
  const diffMins = Math.round(diffSecs / 60)
  const diffHours = Math.round(diffMins / 60)
  const diffDays = Math.round(diffHours / 24)

  // Future dates
  if (diffMs > 0) {
    if (diffMins < 60) return `in ${diffMins} minute${diffMins !== 1 ? 's' : ''}`
    if (diffHours < 24) return `in ${diffHours} hour${diffHours !== 1 ? 's' : ''}`
    if (diffDays < 30) return `in ${diffDays} day${diffDays !== 1 ? 's' : ''}`
    return formatDate(dateString)
  }

  // Past dates
  const absDiffMins = Math.abs(diffMins)
  const absDiffHours = Math.abs(diffHours)
  const absDiffDays = Math.abs(diffDays)

  if (absDiffMins < 1) return 'just now'
  if (absDiffMins < 60) return `${absDiffMins} minute${absDiffMins !== 1 ? 's' : ''} ago`
  if (absDiffHours < 24) return `${absDiffHours} hour${absDiffHours !== 1 ? 's' : ''} ago`
  if (absDiffDays < 30) return `${absDiffDays} day${absDiffDays !== 1 ? 's' : ''} ago`
  return formatDate(dateString)
}

// ============================================================================
// String Utilities
// ============================================================================

/**
 * Truncate text to a maximum length with ellipsis.
 * @param text - Text to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated text with ellipsis if needed
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength).trim() + '...'
}

// ============================================================================
// URL Utilities
// ============================================================================

/**
 * Normalize URL by adding https:// if no protocol is present.
 * @param url - URL string to normalize
 * @returns URL with protocol
 */
export function normalizeUrl(url: string): string {
  const trimmed = url.trim()
  if (!trimmed) return trimmed
  // If already has a protocol (contains ://), return as-is
  if (trimmed.includes('://')) {
    return trimmed
  }
  // Otherwise, prepend https://
  return `https://${trimmed}`
}

/**
 * Validate URL format.
 * @param url - URL string to validate
 * @returns true if URL is valid http/https URL
 */
export function isValidUrl(url: string): boolean {
  try {
    const trimmed = url.trim()
    // URLs should not contain spaces - reject early
    // (Browser URL constructor may encode spaces instead of throwing)
    if (trimmed.includes(' ')) {
      return false
    }
    const normalized = normalizeUrl(trimmed)
    const urlObj = new URL(normalized)
    return urlObj.protocol === 'http:' || urlObj.protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * Extract domain from URL for display.
 * @param url - Full URL
 * @returns Domain without www prefix (includes port if present)
 */
export function getDomain(url: string): string {
  try {
    const urlObj = new URL(url)
    return urlObj.host.replace(/^www\./, '')
  } catch {
    return url
  }
}

/**
 * Get URL without protocol (http:// or https://) for display.
 * @param url - Full URL
 * @returns URL without protocol prefix
 */
export function getUrlWithoutProtocol(url: string): string {
  return url.replace(/^https?:\/\//, '').replace(/^www\./, '')
}

// ============================================================================
// Tag Utilities
// ============================================================================

/**
 * Regex pattern for valid tags: lowercase alphanumeric with hyphens.
 *
 * Note: This validation is intentionally duplicated in the backend (backend/src/schemas/bookmark.py)
 * for security. Frontend validation provides immediate UX feedback. Keep both in sync if
 * changing the tag format rules.
 *
 * Format: lowercase alphanumeric with hyphens (e.g., 'machine-learning', 'web-dev')
 */
export const TAG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/

/**
 * Validate tag format: lowercase alphanumeric with hyphens.
 * @param tag - Tag to validate
 * @returns null if valid, or error message if invalid
 */
export function validateTag(tag: string): string | null {
  const normalized = tag.toLowerCase().trim()
  if (!normalized) return 'Tag cannot be empty'
  if (!TAG_PATTERN.test(normalized)) {
    return 'Tags must be lowercase letters, numbers, and hyphens only'
  }
  return null
}

/**
 * Normalize a tag to lowercase and trimmed.
 * @param tag - Tag to normalize
 * @returns Normalized tag
 */
export function normalizeTag(tag: string): string {
  return tag.toLowerCase().trim()
}

// ============================================================================
// Sorting Utilities
// ============================================================================

import type { ContentList, TagCount } from './types'

export type TagSortOption = 'name-asc' | 'name-desc' | 'count-asc' | 'count-desc'

/**
 * Sort tags by name or count.
 * @param tags - Array of tags to sort
 * @param sortOption - Sort option (name-asc, name-desc, count-asc, count-desc)
 * @returns Sorted copy of tags array
 */
export function sortTags(tags: TagCount[], sortOption: TagSortOption): TagCount[] {
  return [...tags].sort((a, b) => {
    switch (sortOption) {
      case 'name-asc':
        return a.name.localeCompare(b.name)
      case 'name-desc':
        return b.name.localeCompare(a.name)
      case 'count-asc':
        return a.count - b.count || a.name.localeCompare(b.name)
      case 'count-desc':
        return b.count - a.count || a.name.localeCompare(b.name)
    }
  })
}

// ============================================================================
// Filter Expression Utilities
// ============================================================================

/**
 * Extract tags from the first filter group of a content list.
 * Used for pre-populating tags when adding bookmarks from a custom list view.
 *
 * @param list - The content list to extract tags from
 * @returns Array of tags from the first filter group, or undefined if no tags
 *
 * @example
 * // List with filter: (react AND typescript) OR (vue)
 * getFirstGroupTags(list) // returns ['react', 'typescript']
 */
export function getFirstGroupTags(list: ContentList | undefined): string[] | undefined {
  const firstGroup = list?.filter_expression?.groups?.[0]
  return firstGroup?.tags?.length ? firstGroup.tags : undefined
}

/**
 * Archive preset options for scheduling auto-archive dates.
 */
export type ArchivePreset = 'none' | '1-week' | '1-month' | 'end-of-month' | '6-months' | '1-year' | 'custom'

/**
 * Adds months to a date while handling overflow by clamping to the last day of the target month.
 * For example, Jan 31 + 1 month = Feb 28 (not Mar 3).
 *
 * @param baseDate - The starting date
 * @param monthsToAdd - Number of months to add
 * @returns A new Date with months added, clamped to valid day
 */
export function addMonthsWithClamp(baseDate: Date, monthsToAdd: number): Date {
  const targetYear = baseDate.getFullYear() + Math.floor((baseDate.getMonth() + monthsToAdd) / 12)
  const targetMonth = (baseDate.getMonth() + monthsToAdd) % 12
  const date = new Date(targetYear, targetMonth, baseDate.getDate(), 8, 0, 0)
  // If overflow occurred (e.g., Feb 31 → Mar 3), clamp to last day of target month
  if (date.getMonth() !== targetMonth) {
    return new Date(targetYear, targetMonth + 1, 0, 8, 0, 0)
  }
  return date
}

/**
 * Calculates the target date for an archive preset.
 * All dates are set to 8:00 AM local time.
 *
 * @param preset - The archive preset option
 * @param referenceDate - Optional reference date (defaults to now, useful for testing)
 * @returns ISO string of the calculated date, or empty string for 'none'/'custom'
 */
export function calculateArchivePresetDate(preset: ArchivePreset, referenceDate?: Date): string {
  const now = referenceDate ?? new Date()
  let date: Date

  switch (preset) {
    case '1-week':
      date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7, 8, 0, 0)
      break
    case '1-month':
      date = addMonthsWithClamp(now, 1)
      break
    case 'end-of-month':
      // Last day of current month at 8:00 AM
      date = new Date(now.getFullYear(), now.getMonth() + 1, 0, 8, 0, 0)
      break
    case '6-months':
      date = addMonthsWithClamp(now, 6)
      break
    case '1-year':
      date = addMonthsWithClamp(now, 12)
      break
    default:
      return ''
  }
  return date.toISOString()
}
