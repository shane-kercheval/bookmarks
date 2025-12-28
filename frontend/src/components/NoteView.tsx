/**
 * Component for viewing a note with rendered markdown content.
 */
import { useEffect } from 'react'
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
  fullWidth?: boolean
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
  fullWidth = false,
  onEdit,
  onArchive,
  onUnarchive,
  onDelete,
  onRestore,
  onTagClick,
  onBack,
}: NoteViewProps): ReactNode {
  // Keyboard shortcut: 'e' to edit (when not in input)
  useEffect(() => {
    if (!onEdit) return

    const handleKeyDown = (e: KeyboardEvent): void => {
      // Skip if in an input, textarea, or contenteditable
      const activeElement = document.activeElement
      if (
        activeElement?.tagName === 'INPUT' ||
        activeElement?.tagName === 'TEXTAREA' ||
        (activeElement as HTMLElement)?.isContentEditable
      ) {
        return
      }

      // 'e' to edit (without modifiers)
      if (e.key === 'e' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault()
        onEdit()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onEdit])

  return (
    <div className={`flex flex-col h-full w-full ${fullWidth ? '' : 'max-w-4xl mx-auto'}`}>
      {/* Fixed header with back button and actions */}
      <div className="shrink-0 bg-white flex items-center justify-between pb-4 mb-4 border-b border-gray-200">
        <div className="flex items-center gap-2">
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
        </div>

        <div className="flex items-center gap-2">
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

      {/* Scrollable note content */}
      <article className="flex-1 overflow-y-auto min-h-0 pr-2">
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

        {/* Divider between description/tags and content */}
        {note.content && (
          <hr className="border-gray-200 mb-6" />
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
