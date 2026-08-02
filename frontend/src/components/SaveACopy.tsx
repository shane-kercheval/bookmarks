/**
 * Auth-aware "Save a copy" control for the public read view.
 *
 * Three states, driven by auth init status:
 * - initializing  → neutral placeholder (avoids a flash of the wrong button)
 * - authenticated → "Save a copy" (clones via the clone endpoint, then navigates)
 * - anonymous     → "Sign in to save a copy" (login, returning to the in-app
 *                    save route, which fires the clone once they land)
 *
 * Safe on public routes: `AuthProvider` wraps the whole app tree, so the
 * seam hooks resolve everywhere (dev mode included).
 */
import type { ReactNode } from 'react'
import { useAuthStatus } from '../hooks/useAuthStatus'
import { useAuthActions } from '../hooks/useAuthActions'
import { useSavePublicItem } from '../hooks/useSavePublicItem'

type PublicItemType = 'bookmarks' | 'notes' | 'prompts'

interface SaveACopyProps {
  type: PublicItemType
  token: string
}

/**
 * Anonymous-visitor button: sends the user through login, then returns them
 * to the in-app save route (not back to this public page) via `returnTo`
 * (sanitized in AuthProvider before navigation).
 *
 * Why the in-app route and not the current shared URL: the clone needs an
 * authenticated session, and routing through `/app/save-shared` lets the save
 * fire automatically once the user lands post-signup, rather than leaving them
 * back on the public page having to click Save again.
 */
function SignInToSave({ type, token }: SaveACopyProps): ReactNode {
  const { login } = useAuthActions()
  const returnTo = `/app/save-shared/${type}/${token}`

  return (
    <button
      type="button"
      onClick={() => login({ mode: 'login', returnTo })}
      className="btn-secondary whitespace-nowrap"
    >
      Sign in to save
    </button>
  )
}

export function SaveACopy({ type, token }: SaveACopyProps): ReactNode {
  const { isAuthenticated, isLoading } = useAuthStatus()
  const save = useSavePublicItem(type, token)

  if (isLoading) {
    // Neutral placeholder while auth initializes — same footprint as the button.
    return <div className="h-9 w-36 animate-pulse rounded-lg bg-gray-100" aria-hidden="true" />
  }

  if (!isAuthenticated) {
    return <SignInToSave type={type} token={token} />
  }

  return (
    <button
      type="button"
      onClick={() => save.mutate()}
      disabled={save.isPending}
      className="btn-secondary whitespace-nowrap"
    >
      {save.isPending ? 'Saving…' : 'Save to Tiddly'}
    </button>
  )
}
