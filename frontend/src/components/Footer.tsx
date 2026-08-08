import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

/**
 * Footer component with policy and legal links.
 *
 * Displays:
 * - Privacy Policy link
 * - Terms of Service link
 * - License information (GitHub link)
 * - Copyright notice
 *
 * Layout switches on the footer's OWN width (`@container` + `@3xl:` variants),
 * not the viewport. Viewport media queries were wrong wherever the footer sits
 * in a box narrower than the window — with the public share pages' ToC sidebar
 * open, the fixed-height single-row desktop layout stayed active while the
 * links wrapped, clipping them. `@3xl` is 768px, the same threshold the old
 * `md:` variants used, so full-width pages are unchanged.
 */
export function Footer(): ReactNode {
  return (
    <footer className="@container bg-white border-t border-gray-100 mt-auto py-2 @3xl:py-0 @3xl:h-12 shrink-0 flex items-center">
      <div className="max-w-5xl mx-auto px-6 sm:px-8 lg:px-12 w-full">
        <div className="flex flex-col @3xl:flex-row items-center justify-between gap-1 @3xl:gap-0">
          {/* gap-x (not space-x) so wrapped rows stay evenly spaced. */}
          <div className="flex flex-wrap justify-center items-center gap-x-6 gap-y-1 text-sm text-gray-500">
            <Link
              to="/docs"
              className="hover:text-gray-900 transition-colors"
            >
              Docs
            </Link>
            <Link
              to="/privacy"
              className="hover:text-gray-900 transition-colors"
            >
              Privacy Policy
            </Link>
            <Link
              to="/terms"
              className="hover:text-gray-900 transition-colors"
            >
              Terms of Service
            </Link>
            <a
              href="https://github.com/shane-kercheval/tiddly/blob/main/LICENSE"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-900 transition-colors"
            >
              License
            </a>
            <a
              href="https://github.com/shane-kercheval/tiddly"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-900 transition-colors"
            >
              GitHub
            </a>
          </div>
          <div className="text-sm text-gray-400 text-center">
            © 2025 Tiddly. Operated by Shane Kercheval.
          </div>
        </div>
      </div>
    </footer>
  )
}
