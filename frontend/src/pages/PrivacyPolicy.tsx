import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { usePolicyVersions } from '../hooks/usePolicyVersions'

/**
 * Privacy Policy page - public route accessible without authentication.
 *
 * Content mirrors PRIVACY.md in the repository root.
 * Version date is fetched from the backend for single source of truth.
 */
export function PrivacyPolicy(): ReactNode {
  const { versions, isLoading, formatVersionDate } = usePolicyVersions()

  const versionDisplay = isLoading
    ? 'Loading...'
    : versions
      ? formatVersionDate(versions.privacy_policy_version)
      : 'Unknown'

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto bg-white shadow-sm rounded-lg p-8 md:p-12">
        <div className="mb-8">
          <Link
            to="/"
            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
          >
            ← Back to Home
          </Link>
        </div>

        <h1 className="text-4xl font-bold text-gray-900 mb-2">Privacy Policy</h1>
        <p className="text-sm text-gray-600 mb-8">Last Updated: {versionDisplay}</p>

        <div className="prose prose-blue max-w-none space-y-6">
          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Introduction</h2>
            <p className="text-gray-700 leading-relaxed">
              Tiddly ("we", "our", or "us") is operated by Shane Kercheval as an individual. This Privacy Policy explains how we collect, use, and protect your personal information when you use tiddly.me (the "Service").
            </p>
            <p className="text-gray-700 leading-relaxed">
              By using the Service, you agree to the collection and use of information in accordance with this policy.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Information We Collect</h2>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Information You Provide</h3>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li><strong>Account Information:</strong> When you sign up via Auth0, we collect your email address and Auth0 user ID</li>
              <li><strong>Bookmark Data:</strong> URLs, titles, descriptions, and page content you save</li>
              <li><strong>Tags and Lists:</strong> Organization metadata you create</li>
              <li><strong>Personal Access Tokens:</strong> API tokens you generate (stored hashed)</li>
            </ul>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Automatically Collected Information</h3>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li><strong>Usage Data:</strong> When bookmarks were created, updated, and last accessed</li>
              <li><strong>Authentication Data:</strong> Login timestamps and session information (via Auth0)</li>
              <li><strong>Server Logs:</strong> IP addresses, browser type, and access times (Railway infrastructure)</li>
            </ul>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Third-Party Content</h3>
            <p className="text-gray-700 leading-relaxed">
              When you save a bookmark, we automatically fetch and store:
            </p>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>Page title and meta description</li>
              <li>Page content (up to 500KB) for search functionality</li>
              <li>This data is fetched from the URL you provide</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">How We Use Your Information</h2>
            <p className="text-gray-700 leading-relaxed mb-3">We use your data to:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li><strong>Provide the Service:</strong> Store, organize, and search your bookmarks</li>
              <li><strong>Enable Features:</strong> Full-text search, tagging, and custom lists</li>
              <li><strong>Authentication:</strong> Verify your identity via Auth0</li>
              <li><strong>API Access:</strong> Allow programmatic access via Personal Access Tokens</li>
              <li><strong>Improve the Service:</strong> Understand usage patterns (aggregated, not individual)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Data Storage and Security</h2>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Where Your Data is Stored</h3>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li><strong>Database:</strong> PostgreSQL hosted on Railway (US servers)</li>
              <li><strong>Encryption at Rest:</strong> Data is encrypted at storage level by Railway</li>
              <li><strong>Data Isolation:</strong> Multi-tenant architecture ensures your data is separate from other users</li>
            </ul>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Important Security Notes</h3>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>We do <strong>not</strong> use end-to-end encryption because it would prevent search functionality</li>
              <li>The database administrator (Shane Kercheval) has technical ability to access data through database queries</li>
              <li>We will never access your data except when legally required or with your explicit permission</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Your Rights (GDPR)</h2>
            <p className="text-gray-700 leading-relaxed mb-3">
              If you are in the European Union, you have the right to:
            </p>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li><strong>Access:</strong> Request a copy of your data</li>
              <li><strong>Rectification:</strong> Correct inaccurate data</li>
              <li><strong>Erasure:</strong> Delete your account and all data</li>
              <li><strong>Portability:</strong> Export your data in a machine-readable format</li>
              <li><strong>Object:</strong> Object to processing of your data</li>
              <li><strong>Withdraw Consent:</strong> Stop using the service and delete your account</li>
            </ul>
            <p className="text-gray-700 leading-relaxed mt-3">
              To exercise these rights, contact us at <a href="mailto:shane_kercheval@hotmail.com" className="text-blue-600 hover:underline">shane_kercheval@hotmail.com</a> or delete your account in Settings.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Contact Us</h2>
            <div className="bg-gray-50 p-6 rounded-lg">
              <p className="text-gray-700 font-semibold">Shane Kercheval</p>
              <p className="text-gray-700">Email: <a href="mailto:shane_kercheval@hotmail.com" className="text-blue-600 hover:underline">shane_kercheval@hotmail.com</a></p>
              <p className="text-gray-700">GitHub: <a href="https://github.com/shanekercheval/bookmarks" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">github.com/shanekercheval/bookmarks</a></p>
            </div>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Data Controller (GDPR)</h2>
            <div className="bg-gray-50 p-6 rounded-lg">
              <p className="text-gray-700"><strong>Shane Kercheval</strong> (Individual)</p>
              <p className="text-gray-700">Operating: Tiddly</p>
              <p className="text-gray-700">Location: West Richland, WA, USA</p>
              <p className="text-gray-700">Email: <a href="mailto:shane_kercheval@hotmail.com" className="text-blue-600 hover:underline">shane_kercheval@hotmail.com</a></p>
            </div>
          </section>

          <section className="mt-12 pt-8 border-t border-gray-200">
            <p className="text-sm text-gray-600 italic">
              <strong>Consent:</strong> By using Tiddly, you acknowledge that you have read and understood this Privacy Policy and agree to its terms.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
