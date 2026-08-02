import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { usePolicyVersions } from '../hooks/usePolicyVersions'
import { usePageTitle } from '../hooks/usePageTitle'
import { DocsMarkdown } from '../components/markdown/DocsMarkdown'
import { getProseDoc } from '../content/proseDocs'

/**
 * Terms of Service — public route, no authentication required.
 *
 * The terms text is single-sourced as markdown (`content/prose/terms.md`, also
 * served verbatim at `/prose/terms.md` for agents). This component supplies only
 * the public-page chrome and the dynamic "Last Updated" date, which is fetched
 * from the backend (the source of truth for policy versions) and so can't
 * live in the static markdown.
 */
export function TermsOfService(): ReactNode {
  usePageTitle('Terms of Service')
  const { versions, isLoading, formatVersionDate } = usePolicyVersions()
  const doc = getProseDoc('terms')

  const versionDisplay = isLoading
    ? 'Loading...'
    : versions
      ? formatVersionDate(versions.terms_of_service_version)
      : 'Unknown'

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto bg-white shadow-sm rounded-lg p-8 md:p-12">
        <div className="mb-8">
          <Link to="/" className="text-blue-600 hover:text-blue-800 text-sm font-medium">
            ← Back to Home
          </Link>
        </div>
        <DocsMarkdown body={doc.body} />
        <p className="mt-10 border-t border-gray-200 pt-6 text-sm text-gray-600">
          Last Updated: {versionDisplay}
        </p>
      </div>
    </div>
  )
}
