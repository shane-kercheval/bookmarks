import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { usePolicyVersions } from '../hooks/usePolicyVersions'
import { usePageTitle } from '../hooks/usePageTitle'
import { DocsMarkdown } from '../components/markdown/DocsMarkdown'
import { getProseDoc } from '../content/proseDocs'

/**
 * Privacy Policy — public route, no authentication required.
 *
 * The policy text is single-sourced as markdown (`content/prose/privacy.md`, also
 * served verbatim at `/prose/privacy.md` for agents). This component supplies only
 * the public-page chrome and the dynamic "Last Updated" date, which is fetched
 * from the backend (the source of truth for policy versions) and so can't
 * live in the static markdown.
 */
export function PrivacyPolicy(): ReactNode {
  usePageTitle('Privacy Policy')
  const { versions, isLoading, formatVersionDate } = usePolicyVersions()
  const doc = getProseDoc('privacy')

  const versionDisplay = isLoading
    ? 'Loading...'
    : versions
      ? formatVersionDate(versions.privacy_policy_version)
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
