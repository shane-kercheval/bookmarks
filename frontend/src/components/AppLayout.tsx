import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'

/**
 * Routing level for all authenticated app routes.
 *
 * A pass-through since the consent gate was removed (2026-08-01) — it used to
 * check consent status and mount the blocking dialog. The nesting level itself
 * is load-bearing and must not be collapsed: `/app/save-shared/:type/:token` is
 * registered as a SIBLING of `Layout` rather than a child, so it renders here
 * without triggering the app shell's sidebar, filters, and tags fetches. Delete
 * this component and that route inherits those fetches.
 *
 * See docs/implementation_plans/2026-08-01-consent-simplification.md.
 */
export function AppLayout(): ReactNode {
  return <Outlet />
}
