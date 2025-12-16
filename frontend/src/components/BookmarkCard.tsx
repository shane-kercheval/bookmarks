/**
 * Component for displaying a single bookmark card.
 */
import type { ReactNode } from 'react'
import type { Bookmark } from '../types'
import { formatDate, truncate, getDomain, getUrlWithoutProtocol } from '../utils'

interface BookmarkCardProps {
  bookmark: Bookmark
  view?: 'active' | 'archived' | 'deleted'
  onEdit?: (bookmark: Bookmark) => void
  onDelete: (bookmark: Bookmark) => void
  onArchive?: (bookmark: Bookmark) => void
  onUnarchive?: (bookmark: Bookmark) => void
  onRestore?: (bookmark: Bookmark) => void
  onTagClick?: (tag: string) => void
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
  onEdit,
  onDelete,
  onArchive,
  onUnarchive,
  onRestore,
  onTagClick,
}: BookmarkCardProps): ReactNode {
  const hasTitle = !!bookmark.title
  const displayTitle = bookmark.title || getDomain(bookmark.url)
  const urlDisplay = getUrlWithoutProtocol(bookmark.url)
  const domain = getDomain(bookmark.url)
  const faviconUrl = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`

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
              className="shrink-0"
            >
              <img
                src={faviconUrl}
                alt=""
                className="w-4 h-4"
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                }}
              />
            </a>
            <a
              href={bookmark.url}
              target="_blank"
              rel="noopener noreferrer"
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
                className="text-sm text-gray-400 hover:text-gray-600 transition-colors truncate max-w-md"
                title={bookmark.url}
              >
                {urlDisplay}
              </a>
            )}
          </div>

          {/* Description */}
          {bookmark.description && (
            <p className="mt-1 text-sm text-gray-500 leading-relaxed line-clamp-2">
              {bookmark.description}
            </p>
          )}
        </div>

        {/* Tags */}
        {bookmark.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 justify-end w-32 shrink-0">
            {bookmark.tags.map((tag) => (
              <button
                key={tag}
                onClick={() => onTagClick?.(tag)}
                className="badge-secondary hover:bg-gray-100 hover:border-gray-300 transition-colors"
                title={`Filter by tag: ${tag}`}
              >
                {tag}
              </button>
            ))}
          </div>
        )}

        {/* Actions and date */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex">
            {/* Edit button - shown in active and archived views */}
            {view !== 'deleted' && onEdit && (
              <button
                onClick={() => onEdit(bookmark)}
                className="btn-icon"
                title="Edit bookmark"
                aria-label="Edit bookmark"
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
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                  />
                </svg>
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
            <button
              onClick={() => onDelete(bookmark)}
              className="btn-icon-danger"
              title={view === 'deleted' ? 'Delete permanently' : 'Delete bookmark'}
              aria-label={view === 'deleted' ? 'Delete permanently' : 'Delete bookmark'}
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
          </div>
          <span className="text-xs text-gray-400">
            {formatDate(bookmark.created_at)}
          </span>
        </div>
      </div>
    </div>
  )
}
