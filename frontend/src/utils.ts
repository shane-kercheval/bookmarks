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

/** Regex pattern for valid tags: lowercase alphanumeric with hyphens */
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
