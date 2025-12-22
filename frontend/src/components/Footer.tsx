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
 */
export function Footer(): ReactNode {
  return (
    <footer className="bg-white border-t border-gray-200 mt-auto">
      <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row items-center justify-between space-y-4 md:space-y-0">
          <div className="flex items-center space-x-6 text-sm text-gray-600">
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
              href="https://github.com/shane-kercheval/bookmarks/blob/main/LICENSE"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-900 transition-colors"
            >
              License
            </a>
            <a
              href="https://github.com/shane-kercheval/bookmarks"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-900 transition-colors"
            >
              GitHub
            </a>
          </div>
          <div className="text-sm text-gray-500">
            © 2025 Tiddly. Operated by Shane Kercheval.
          </div>
        </div>
      </div>
    </footer>
  )
}
