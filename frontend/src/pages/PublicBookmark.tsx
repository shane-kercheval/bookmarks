/**
 * Public read-only view of a shared bookmark.
 *
 * Route: /shared/bookmarks/:token (under PublicPageLayout, no auth required).
 *
 * Thin wrapper: fetch by token via the no-auth client, adapt the locked-down
 * public payload to the shape the existing `Bookmark` render component expects,
 * and render it in `readOnly` mode. Shared chrome lives in PublicItemShell.
 */
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { Bookmark as BookmarkComponent } from '../components/Bookmark'
import { PublicItemShell } from '../components/PublicItemShell'
import { usePublicBookmark } from '../hooks/usePublicItem'
import type { Bookmark as BookmarkType, PublicBookmark as PublicBookmarkType } from '../types'

const noopSave = async (): Promise<void> => {}
const noopClose = (): void => {}

/** Adapt the public payload to the owner-shaped Bookmark the render component expects. */
function toBookmark(data: PublicBookmarkType): BookmarkType {
  return {
    id: '',
    url: data.url,
    title: data.title,
    description: data.description,
    summary: null,
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

export function PublicBookmark(): ReactNode {
  const { token } = useParams<{ token: string }>()
  const { data, isLoading, isError, error, refetch } = usePublicBookmark(token)

  return (
    <PublicItemShell
      type="bookmarks"
      token={token ?? ''}
      isLoading={isLoading}
      isError={isError}
      error={error}
      onRetry={() => { void refetch() }}
      isArchived={data?.is_archived ?? false}
    >
      {data && (
        <BookmarkComponent
          bookmark={toBookmark(data)}
          tagSuggestions={[]}
          onSave={noopSave}
          onClose={noopClose}
          readOnly
          viewState={data.is_archived ? 'archived' : 'active'}
          aiAvailable={false}
        />
      )}
    </PublicItemShell>
  )
}
