/**
 * Public read-only view of a shared prompt.
 *
 * Route: /shared/prompts/:token (under PublicSharedTocLayout, no auth required).
 *
 * Thin wrapper: fetch by token via the no-auth client, adapt the locked-down
 * public payload to the shape the existing `Prompt` render component expects,
 * and render it in `readOnly` mode. The prompt's Jinja template renders through
 * the same read-only CodeMirror path as the authenticated view (with Jinja
 * highlighting); shared chrome lives in PublicItemShell.
 */
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { Prompt as PromptComponent } from '../components/Prompt'
import { PublicItemShell } from '../components/PublicItemShell'
import { usePublicPrompt } from '../hooks/usePublicItem'
import type { Prompt as PromptType, PublicPrompt as PublicPromptType } from '../types'

const noopSave = async (): Promise<void> => {}
const noopClose = (): void => {}

/** Adapt the public payload to the owner-shaped Prompt the render component expects. */
function toPrompt(data: PublicPromptType): PromptType {
  return {
    id: '',
    name: data.name,
    title: data.title,
    description: data.description,
    arguments: data.arguments,
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

export function PublicPrompt(): ReactNode {
  const { token } = useParams<{ token: string }>()
  const { data, isLoading, isError, error, refetch } = usePublicPrompt(token)

  return (
    <PublicItemShell
      type="prompts"
      token={token ?? ''}
      isLoading={isLoading}
      isError={isError}
      error={error}
      onRetry={() => { void refetch() }}
      isArchived={data?.is_archived ?? false}
      tocEnabled
    >
      {data && (
        <PromptComponent
          prompt={toPrompt(data)}
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
