/**
 * Public read-only view of a shared note.
 *
 * Route: /shared/notes/:token (under PublicSharedTocLayout, no auth required).
 *
 * Thin wrapper: fetch by token via the no-auth client, adapt the locked-down
 * public payload to the shape the existing `Note` render component expects, and
 * render it in `readOnly` mode. All shared chrome (loading, not-found, archived
 * banner, Save-a-copy) lives in PublicItemShell.
 */
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { Note as NoteComponent } from '../components/Note'
import { PublicItemShell } from '../components/PublicItemShell'
import { usePublicNote } from '../hooks/usePublicItem'
import type { Note as NoteType, PublicNote as PublicNoteType } from '../types'

const noopSave = async (): Promise<void> => {}
const noopClose = (): void => {}

/** Adapt the public payload to the owner-shaped Note the render component expects. */
function toNote(data: PublicNoteType): NoteType {
  return {
    id: '',
    title: data.title,
    description: data.description,
    tags: [],
    created_at: data.created_at,
    updated_at: data.updated_at,
    last_used_at: data.created_at,
    deleted_at: null,
    // Synthesized so internal archive checks agree with the public is_archived
    // flag; the raw timestamp isn't exposed publicly and isn't shown in readOnly.
    archived_at: data.is_archived ? data.created_at : null,
    content_preview: null,
    content: data.content,
    // Owner-only sharing fields are absent from the public payload and unused in
    // readOnly (no share toolbar); synthesize the unshared default.
    is_public: false,
    public_token: null,
  }
}

export function PublicNote(): ReactNode {
  const { token } = useParams<{ token: string }>()
  const { data, isLoading, isError, error, refetch } = usePublicNote(token)

  return (
    <PublicItemShell
      type="notes"
      token={token ?? ''}
      isLoading={isLoading}
      isError={isError}
      error={error}
      onRetry={() => { void refetch() }}
      isArchived={data?.is_archived ?? false}
      tocEnabled
    >
      {data && (
        <NoteComponent
          note={toNote(data)}
          tagSuggestions={[]}
          onSave={noopSave}
          onClose={noopClose}
          readOnly
          viewState={data.is_archived ? 'archived' : 'active'}
          aiAvailable={false}
          showTocToggle
        />
      )}
    </PublicItemShell>
  )
}
