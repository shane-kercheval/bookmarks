/**
 * Component for displaying a single bookmark card.
 */
import type { ReactNode } from 'react'
import type { Bookmark } from '../types'
import { formatDate, truncate, getDomain } from '../utils'

interface BookmarkCardProps {
  bookmark: Bookmark
  onEdit: (bookmark: Bookmark) => void
  onDelete: (bookmark: Bookmark) => void
  onTagClick?: (tag: string) => void
}

/**
 * BookmarkCard displays a single bookmark with its metadata.
 *
 * Features:
 * - Clickable title/URL opens in new tab
 * - Edit and delete buttons
 * - Clickable tags for filtering
 * - Truncated description
 */
export function BookmarkCard({
  bookmark,
  onEdit,
  onDelete,
  onTagClick,
}: BookmarkCardProps): ReactNode {
  const displayTitle = bookmark.title || getDomain(bookmark.url)
  const domain = getDomain(bookmark.url)

  return (
    <div className="card">
      {/* Header: Title and actions */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Title - links to URL */}
          <a
            href={bookmark.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-lg font-medium text-blue-600 hover:text-blue-800 hover:underline"
            title={bookmark.url}
          >
            {truncate(displayTitle, 60)}
          </a>

          {/* Domain/URL */}
          <a
            href={bookmark.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-0.5 block text-sm text-gray-500 hover:text-gray-700"
          >
            {domain}
          </a>
        </div>

        {/* Action buttons */}
        <div className="flex shrink-0 gap-1">
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
        </div>
      </div>

      {/* Description */}
      {bookmark.description && (
        <p className="mt-2 text-sm text-gray-600">
          {truncate(bookmark.description, 150)}
        </p>
      )}

      {/* Tags and date row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {/* Tags */}
        {bookmark.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {bookmark.tags.map((tag) => (
              <button
                key={tag}
                onClick={() => onTagClick?.(tag)}
                className="badge-secondary hover:bg-gray-200"
                title={`Filter by tag: ${tag}`}
              >
                {tag}
              </button>
            ))}
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Date */}
        <span className="text-xs text-gray-400">
          {formatDate(bookmark.created_at)}
        </span>
      </div>
    </div>
  )
}
