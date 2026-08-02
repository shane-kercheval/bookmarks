/**
 * In-app save route for the public "Save to Tiddly" flow.
 *
 * Reached one way: a logged-out visitor clicks "Sign in to save" on a shared
 * page, and the sign-in returns them here via `appState.returnTo` (SaveACopy's
 * anonymous branch). They read the public page with no auth, click Save, sign
 * up, land here, and this route fires the clone once and takes them to their
 * new copy.
 *
 * Registered under `AppLayout` but *outside* `Layout`, so it renders without
 * kicking off the app shell's sidebar/filters/tags fetches — see AppLayout for
 * why that nesting level still exists.
 *
 * It used to be reachable a second way, from `useSavePublicItem` redirecting
 * here on a 451 so the consent dialog could collect acceptance before the
 * clone. The consent gate was removed on 2026-08-01 and that path is gone.
 */
import { useEffect, useRef, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useSavePublicItem } from '../hooks/useSavePublicItem'
import { LoadingSpinnerPage } from '../components/ui'

type PublicItemType = 'bookmarks' | 'notes' | 'prompts'
const PUBLIC_ITEM_TYPES: readonly PublicItemType[] = ['bookmarks', 'notes', 'prompts']

function isPublicItemType(value: string | undefined): value is PublicItemType {
  return value !== undefined && (PUBLIC_ITEM_TYPES as readonly string[]).includes(value)
}

/**
 * Outer route component: validate the URL params, then hand off to the runner
 * with a typed `type`. Splitting this out keeps `useSavePublicItem` (which takes
 * a typed union) from ever being called with a raw, unvalidated route param.
 */
export function SaveSharedRedirect(): ReactNode {
  const { type, token } = useParams<{ type: string; token: string }>()
  const navigate = useNavigate()
  const valid = isPublicItemType(type) && !!token

  useEffect(() => {
    // A garbled URL has nothing to save — send the user to their content list.
    if (!valid) {
      navigate('/app/content', { replace: true })
    }
  }, [valid, navigate])

  if (!isPublicItemType(type) || !token) {
    return <LoadingSpinnerPage label="Saving…" />
  }

  return <SaveSharedRunner type={type} token={token} />
}

function SaveSharedRunner({ type, token }: { type: PublicItemType; token: string }): ReactNode {
  const navigate = useNavigate()
  const { mutate, isError } = useSavePublicItem(type, token)
  const firedRef = useRef(false)

  // Fire the clone exactly once, on mount. No readiness gate is needed — this
  // route renders under ProtectedRoute, which withholds its Outlet until auth
  // has resolved. The ref (not state) guard stops a re-render or a StrictMode
  // double-invoke from cloning the (non-idempotent) item twice.
  useEffect(() => {
    if (firedRef.current) return
    firedRef.current = true
    mutate()
  }, [mutate])

  // Error landing. The hook owns success (it navigates to the new copy) and
  // already toasted the failure, so here we only pick the landing page.
  useEffect(() => {
    if (!isError) return
    navigate('/app/content', { replace: true })
  }, [isError, navigate])

  return <LoadingSpinnerPage label="Saving…" />
}
