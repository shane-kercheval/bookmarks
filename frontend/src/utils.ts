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
// Filter Expression Utilities
// ============================================================================

import type { BookmarkList } from './types'

/**
 * Extract tags from the first filter group of a bookmark list.
 * Used for pre-populating tags when adding bookmarks from a custom list view.
 *
 * @param list - The bookmark list to extract tags from
 * @returns Array of tags from the first filter group, or undefined if no tags
 *
 * @example
 * // List with filter: (react AND typescript) OR (vue)
 * getFirstGroupTags(list) // returns ['react', 'typescript']
 */
export function getFirstGroupTags(list: BookmarkList | undefined): string[] | undefined {
  const firstGroup = list?.filter_expression?.groups?.[0]
  return firstGroup?.tags?.length ? firstGroup.tags : undefined
}
