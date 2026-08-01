/**
 * Shared chrome for the public read view, wrapping the reused detail render
 * component (`Note` / `Bookmark` / `Prompt` in `readOnly` mode).
 *
 * Owns the cross-cutting pieces every shared page needs — loading state,
 * not-found state, the "archived" banner, and the auth-aware Save-a-copy bar —
 * so the per-type page wrappers stay thin (fetch + adapt + render).
 */
import type { ReactNode } from 'react'
import axios from 'axios'
import { Link } from 'react-router-dom'
import { LoadingSpinner } from './ui'
import { SaveACopy } from './SaveACopy'
import { useAuthStatus } from '../hooks/useAuthStatus'

type PublicItemType = 'bookmarks' | 'notes' | 'prompts'

interface PublicItemShellProps {
  type: PublicItemType
  token: string
  isLoading: boolean
  isError: boolean
  /** The query error (used to distinguish a real 404 from transient failures). */
  error?: unknown
  /** Retry the fetch (shown for transient errors). */
  onRetry?: () => void
  isArchived: boolean
  children: ReactNode
}

export function PublicItemShell({
  type,
  token,
  isLoading,
  isError,
  error,
  onRetry,
  isArchived,
  children,
}: PublicItemShellProps): ReactNode {
  // Drives the "what is Tiddly?" blurb, shown only to logged-out visitors who
  // may not recognize the product. (In dev mode the user is always
  // "authenticated", so the blurb only appears against a real signed-in session.)
  const { isAuthenticated, isLoading: authLoading } = useAuthStatus()

  if (isLoading) {
    return (
      <div className="flex justify-center py-24">
        <LoadingSpinner size="lg" label="Loading shared item..." />
      </div>
    )
  }

  if (isError) {
    const status = axios.isAxiosError(error) ? error.response?.status : undefined

    // A real 404 means the token is unknown / unpublished / deleted — i.e. gone.
    if (status === 404) {
      return (
        <div className="mx-auto max-w-md py-24 text-center">
          <h1 className="text-lg font-semibold text-gray-900">This shared item isn’t available</h1>
          <p className="mt-2 text-sm text-gray-500">
            The link may be incorrect, or its owner may have stopped sharing it.
          </p>
          <Link to="/" className="mt-6 inline-block text-sm font-medium text-gray-900 underline">
            Go to Tiddly
          </Link>
        </div>
      )
    }

    // Anything else (rate limit, server error, network) is transient — don't
    // imply the owner revoked access.
    const message = status === 429
      ? 'You’re loading shared items too quickly. Please wait a moment and try again.'
      : 'We couldn’t load this shared item. Please check your connection and try again.'
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="text-lg font-semibold text-gray-900">Couldn’t load this item</h1>
        <p className="mt-2 text-sm text-gray-500">{message}</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="btn-secondary mt-6">
            Try again
          </button>
        )}
      </div>
    )
  }

  const showBlurb = !authLoading && !isAuthenticated

  return (
    // Pull up on mobile to trim the layout's generous top padding, which is too
    // much above the share content on small screens (desktop unchanged).
    <div className="-mt-6 sm:mt-0">
      {isArchived && (
        <div className="mb-3">
          <span className="inline-flex items-center rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
            Archived
          </span>
        </div>
      )}

      {/* Primary action, left-aligned above the content so it's obvious. The
          blurb explains the product to logged-out visitors who land here cold. */}
      <div className="mb-3 sm:mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <SaveACopy type={type} token={token} />
        {showBlurb && (
          <p className="text-sm text-gray-500">
            Tiddly is a home for your bookmarks, notes, and prompts.{' '}
            <Link to="/features" target="_blank" rel="noopener noreferrer" className="font-medium text-gray-700 underline">Learn more</Link>
          </p>
        )}
      </div>
      {children}
    </div>
  )
}
