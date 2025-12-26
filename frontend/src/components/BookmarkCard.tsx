/**
 * Component for displaying a single bookmark card.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { BookmarkListItem } from '../types'
import type { SortByOption } from '../constants/sortOptions'
import { formatDate, truncate, getDomain, getUrlWithoutProtocol } from '../utils'
import { ConfirmDeleteButton } from './ui'

interface BookmarkCardProps {
  bookmark: BookmarkListItem
  view?: 'active' | 'archived' | 'deleted'
  sortBy?: SortByOption
  onEdit?: (bookmark: BookmarkListItem) => void
  onDelete: (bookmark: BookmarkListItem) => void
  onArchive?: (bookmark: BookmarkListItem) => void
  onUnarchive?: (bookmark: BookmarkListItem) => void
  onRestore?: (bookmark: BookmarkListItem) => void
  onTagClick?: (tag: string) => void
  onTagRemove?: (bookmark: BookmarkListItem, tag: string) => void
  onLinkClick?: (bookmark: BookmarkListItem) => void
  /** Called when user cancels a scheduled auto-archive */
  onCancelScheduledArchive?: (bookmark: BookmarkListItem) => void
  /** Whether the edit action is currently loading (fetching full bookmark) */
  isLoading?: boolean
}

/**
 * BookmarkCard displays a single bookmark with its metadata.
 *
 * Features:
 * - Clickable title/URL opens in new tab
 * - Context-aware action buttons based on view:
 *   - active: edit, archive, delete
 *   - archived: edit, restore, delete
 *   - deleted: restore, permanent delete
 * - Clickable tags for filtering
 * - Truncated description
 */
export function BookmarkCard({
  bookmark,
  view = 'active',
  sortBy = 'created_at',
  onEdit,
  onDelete,
  onArchive,
  onUnarchive,
  onRestore,
  onTagClick,
  onTagRemove,
  onLinkClick,
  onCancelScheduledArchive,
  isLoading = false,
}: BookmarkCardProps): ReactNode {
  const hasTitle = !!bookmark.title
  const displayTitle = bookmark.title || getDomain(bookmark.url)
  const urlDisplay = getUrlWithoutProtocol(bookmark.url)
  const domain = getDomain(bookmark.url)
  const faviconUrl = `https://icons.duckduckgo.com/ip3/${domain}.ico`
  const defaultFavicon = `data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%239CA3AF" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`

  // Dynamic date display based on current sort option
  const getDateDisplay = (): string => {
    switch (sortBy) {
      case 'updated_at':
        return `Modified: ${formatDate(bookmark.updated_at)}`
      case 'last_used_at':
        return `Used: ${formatDate(bookmark.last_used_at)}`
      case 'created_at':
      case 'title':
      default:
        return `Created: ${formatDate(bookmark.created_at)}`
    }
  }

  // Check if bookmark has a scheduled future archive date
  const hasScheduledArchive = view === 'active' &&
    bookmark.archived_at &&
    new Date(bookmark.archived_at) > new Date()

  // State for copy button feedback
  const [copySuccess, setCopySuccess] = useState(false)

  // Track usage when link is clicked (unless shift+modifier key is held for silent mode)
  const handleLinkClick = (e: React.MouseEvent): void => {
    // Skip tracking if shift+cmd/ctrl held (silent mode: open without tracking)
    if (e.shiftKey && (e.metaKey || e.ctrlKey)) {
      return
    }
    onLinkClick?.(bookmark)
  }

  // Copy URL to clipboard with visual feedback
  const handleCopyUrl = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(bookmark.url)
      setCopySuccess(true)
      // Track usage when copying
      onLinkClick?.(bookmark)
      // Reset after brief flash
      setTimeout(() => setCopySuccess(false), 1000)
    } catch {
      // Silently fail - clipboard API may not be available
    }
  }

  return (
    <div className="card">
      <div className="flex items-start gap-4">
        {/* Main content */}
        <div className="min-w-0 flex-1">
          {/* Title and URL row */}
          <div className="flex items-center gap-2 flex-wrap">
            <a
              href={bookmark.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={handleLinkClick}
              className="shrink-0"
            >
              <img
                src={faviconUrl}
                alt=""
                className="w-4 h-4"
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.src = defaultFavicon
                }}
              />
            </a>
            <a
              href={bookmark.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={handleLinkClick}
              className="text-base font-medium text-gray-900 hover:text-gray-600 transition-colors"
              title={bookmark.url}
            >
              {truncate(displayTitle, 60)}
            </a>
            {hasTitle && (
              <a
                href={bookmark.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={handleLinkClick}
                className="text-sm text-gray-400 hover:text-gray-600 transition-colors truncate max-w-md"
                title={bookmark.url}
              >
                {urlDisplay}
              </a>
            )}
          </div>

          {/* Description */}
          {bookmark.description && (
            <p className="mt-1 text-sm text-gray-500 truncate">
              {bookmark.description}
            </p>
          )}
        </div>

        {/* Tags */}
        {bookmark.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 justify-end w-32 shrink-0">
            {bookmark.tags.map((tag) => (
              <div key={tag} className="group relative">
                <button
                  onClick={() => onTagClick?.(tag)}
                  className="badge-secondary hover:bg-gray-100 hover:border-gray-300 transition-colors"
                  title={`Filter by tag: ${tag}`}
                >
                  {tag}
                </button>
                {onTagRemove && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onTagRemove(bookmark, tag)
                    }}
                    className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-gray-500 hover:bg-red-500 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                    title={`Remove tag: ${tag}`}
                    aria-label={`Remove tag ${tag}`}
                  >
                    <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Actions and date */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex">
            {/* Copy URL button */}
            <button
              onClick={handleCopyUrl}
              className={`btn-icon transition-colors ${copySuccess ? 'text-green-600' : ''}`}
              title="Copy URL"
              aria-label="Copy URL"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                />
              </svg>
            </button>

            {/* Edit button - shown in active and archived views */}
            {view !== 'deleted' && onEdit && (
              <button
                onClick={() => onEdit(bookmark)}
                className="btn-icon"
                title="Edit bookmark"
                aria-label="Edit bookmark"
                disabled={isLoading}
              >
                {isLoading ? (
                  <div className="spinner-sm" />
                ) : (
                  <svg
                    className="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                    />
                  </svg>
                )}
              </button>
            )}

            {/* Archive button - shown in active view */}
            {view === 'active' && onArchive && (
              <button
                onClick={() => onArchive(bookmark)}
                className="btn-icon"
                title="Archive bookmark"
                aria-label="Archive bookmark"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
                  />
                </svg>
              </button>
            )}

            {/* Restore button - shown in archived view (unarchive action) */}
            {view === 'archived' && onUnarchive && (
              <button
                onClick={() => onUnarchive(bookmark)}
                className="btn-icon"
                title="Restore bookmark"
                aria-label="Restore bookmark"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
                  />
                </svg>
              </button>
            )}

            {/* Restore button - shown in deleted view */}
            {view === 'deleted' && onRestore && (
              <button
                onClick={() => onRestore(bookmark)}
                className="btn-icon"
                title="Restore bookmark"
                aria-label="Restore bookmark"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
                  />
                </svg>
              </button>
            )}

            {/* Delete button - shown in all views */}
            {/* Use ConfirmDeleteButton for permanent delete in trash view */}
            {view === 'deleted' ? (
              <ConfirmDeleteButton
                onConfirm={() => onDelete(bookmark)}
                title="Delete permanently"
              />
            ) : (
              <button
                onClick={() => onDelete(bookmark)}
                className="btn-icon-danger"
                title="Delete bookmark"
                aria-label="Delete bookmark"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </button>
            )}
          </div>
          <div className="flex flex-col items-end gap-0.5">
            <span className="text-xs text-gray-400">
              {getDateDisplay()}
            </span>
            {hasScheduledArchive && bookmark.archived_at && (
              <span className="flex items-center gap-1 text-xs text-amber-600">
                <span>Archiving: {formatDate(bookmark.archived_at)}</span>
                {onCancelScheduledArchive && (
                  <button
                    onClick={() => onCancelScheduledArchive(bookmark)}
                    className="text-amber-500 hover:text-amber-700 transition-colors p-0.5 -m-0.5"
                    title="Cancel scheduled archive"
                    aria-label="Cancel scheduled archive"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
