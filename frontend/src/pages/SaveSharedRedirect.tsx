/**
 * In-app save route for the public "Save to Tiddly" flow.
 *
 * Reached two ways, both of which need consent collected before the clone runs:
 * - A logged-out visitor clicks "Sign in to save" on a shared page; the sign-in
 *   returns them here via `appState.returnTo` (SaveACopy's anonymous branch).
 * - A logged-in-but-unconsented user clicks Save in place; `useSavePublicItem`
 *   redirects here on the resulting 451.
 *
 * This route is registered under `AppLayout` but *outside* `Layout`, so it gets
 * AppLayout's consent enforcement (the existing `ConsentDialog`) without kicking
 * off the app shell's sidebar/filters/tags fetches. The new user reads (no auth)
 * → clicks Save → signs up → AppLayout collects consent → this route fires the
 * clone once and lands them on their new copy. No consent UI is added to the
 * public page.
 */
import { useEffect, useRef, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import axios from 'axios'
import toast from 'react-hot-toast'
import { isDevMode } from '../config'
import { useConsentStore } from '../stores/consentStore'
import { useSavePublicItem } from '../hooks/useSavePublicItem'
import { LoadingSpinnerPage } from '../components/ui'

type PublicItemType = 'bookmarks' | 'notes' | 'prompts'
const PUBLIC_ITEM_TYPES: readonly PublicItemType[] = ['bookmarks', 'notes', 'prompts']

function isPublicItemType(value: string | undefined): value is PublicItemType {
  return value !== undefined && (PUBLIC_ITEM_TYPES as readonly string[]).includes(value)
}

/**
 * How long to wait for the consent check to settle before giving up. This guards
 * ONLY the readiness wait — the window before the save fires — not the in-flight
 * clone (see SaveSharedRunner). A hung consent check shouldn't strand the user
 * on a "Saving…" spinner forever.
 */
const CONSENT_READINESS_TIMEOUT_MS = 15_000

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
  const needsConsent = useConsentStore((state) => state.needsConsent)
  // Mirror Layout.tsx's readiness gate: dev mode bypasses consent entirely
  // (needsConsent stays null), otherwise wait for the check to resolve to false.
  // Plain `needsConsent === false` would spin forever in dev mode.
  const consentReady = isDevMode || needsConsent === false
  const { mutate, isError, error } = useSavePublicItem(type, token)
  const firedRef = useRef(false)

  // Fire the clone exactly once, only after consent is ready. A ref (not state)
  // guard so a re-render, StrictMode double-invoke, or needsConsent simply
  // staying false across renders can't clone the (non-idempotent) item twice.
  useEffect(() => {
    if (!consentReady || firedRef.current) return
    firedRef.current = true
    mutate()
  }, [consentReady, mutate])

  // Timeout guards ONLY the readiness wait. It's armed while we haven't fired
  // yet and cleared the moment we do (the fire effect above runs first on the
  // readiness-flip render, so firedRef is already true when this re-runs) — and
  // on unmount. We must never abort an in-flight clone: it's non-idempotent, and
  // the save hook already navigates on success / toasts on failure.
  useEffect(() => {
    if (firedRef.current) return
    const timer = setTimeout(() => {
      toast.error('Saving is taking longer than expected — please try again.')
      navigate('/app/content', { replace: true })
    }, CONSENT_READINESS_TIMEOUT_MS)
    return () => clearTimeout(timer)
  }, [consentReady, navigate])

  // Error landing. The hook owns success (it navigates to the new copy) and
  // already toasted any genuine failure, so here we only pick the landing page.
  useEffect(() => {
    if (!isError) return
    const status = axios.isAxiosError(error) ? error.response?.status : undefined
    // 451 is the consent path, NOT a hard failure: the global interceptor flips
    // needsConsent=true, AppLayout swaps in the ConsentDialog (unmounting this
    // route), and after the user accepts the route remounts and the save
    // succeeds. Navigating to /app/content here would yank them off the dialog.
    if (status === 451) return
    navigate('/app/content', { replace: true })
  }, [isError, error, navigate])

  return <LoadingSpinnerPage label="Saving…" />
}
