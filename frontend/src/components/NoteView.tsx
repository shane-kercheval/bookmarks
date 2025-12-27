/**
 * Component for viewing a note with rendered markdown content.
 */
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import type { Note } from '../types'
import { formatDate } from '../utils'
import { EditIcon, ArchiveIcon, RestoreIcon, TrashIcon } from './icons'

interface NoteViewProps {
  note: Note
  view?: 'active' | 'archived' | 'deleted'
  onEdit?: () => void
  onArchive?: () => void
  onUnarchive?: () => void
  onDelete?: () => void
  onRestore?: () => void
  onTagClick?: (tag: string) => void
  onBack?: () => void
}

/**
 * NoteView displays a note with rendered markdown content.
 *
 * Features:
 * - Renders markdown using react-markdown with GFM support
 * - XSS protection via rehype-sanitize
 * - Shows title, description, tags, and metadata
 * - Edit button to switch to edit mode
 * - Context-aware actions based on view state
 */
export function NoteView({
  note,
  view = 'active',
  onEdit,
  onArchive,
  onUnarchive,
  onDelete,
  onRestore,
  onTagClick,
  onBack,
}: NoteViewProps): ReactNode {
  return (
    <div className="max-w-4xl mx-auto">
      {/* Header with back button and actions */}
      <div className="flex items-center justify-between mb-6">
        {onBack && (
          <button
            onClick={onBack}
            className="btn-secondary flex items-center gap-2"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back
          </button>
        )}

        <div className="flex items-center gap-2">
          {/* Edit button - shown in active and archived views */}
          {view !== 'deleted' && onEdit && (
            <button
              onClick={onEdit}
              className="btn-primary flex items-center gap-2"
            >
              <EditIcon />
              Edit
            </button>
          )}

          {/* Archive button - shown in active view */}
          {view === 'active' && onArchive && (
            <button
              onClick={onArchive}
              className="btn-secondary flex items-center gap-2"
              title="Archive note"
            >
              <ArchiveIcon className="h-4 w-4" />
              Archive
            </button>
          )}

          {/* Unarchive button - shown in archived view */}
          {view === 'archived' && onUnarchive && (
            <button
              onClick={onUnarchive}
              className="btn-secondary flex items-center gap-2"
              title="Restore note"
            >
              <RestoreIcon />
              Restore
            </button>
          )}

          {/* Restore button - shown in deleted view */}
          {view === 'deleted' && onRestore && (
            <button
              onClick={onRestore}
              className="btn-primary flex items-center gap-2"
              title="Restore note"
            >
              <RestoreIcon />
              Restore
            </button>
          )}

          {/* Delete button */}
          {onDelete && (
            <button
              onClick={onDelete}
              className="btn-secondary text-red-600 hover:text-red-700 hover:border-red-300 flex items-center gap-2"
              title={view === 'deleted' ? 'Delete permanently' : 'Delete note'}
            >
              <TrashIcon />
              {view === 'deleted' ? 'Delete Permanently' : 'Delete'}
            </button>
          )}
        </div>
      </div>

      {/* Note content */}
      <article className="card">
        {/* Title */}
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          {note.title}
        </h1>

        {/* Metadata row */}
        <div className="flex items-center gap-4 text-sm text-gray-500 mb-4">
          <span>Created: {formatDate(note.created_at)}</span>
          {note.updated_at !== note.created_at && (
            <span>Updated: {formatDate(note.updated_at)}</span>
          )}
          {note.version > 1 && (
            <span className="text-gray-400">v{note.version}</span>
          )}
        </div>

        {/* Tags */}
        {note.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-6">
            {note.tags.map((tag) => (
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

        {/* Description */}
        {note.description && (
          <p className="text-gray-600 italic border-l-4 border-gray-200 pl-4 mb-6">
            {note.description}
          </p>
        )}

        {/* Markdown content */}
        {note.content ? (
          <div className="prose prose-gray max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeSanitize]}
            >
              {note.content}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="text-gray-400 italic">No content</p>
        )}
      </article>
    </div>
  )
}
