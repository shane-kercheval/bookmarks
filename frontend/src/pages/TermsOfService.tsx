import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { usePolicyVersions } from '../hooks/usePolicyVersions'

/**
 * Terms of Service page - public route accessible without authentication.
 *
 * Content mirrors TERMS.md in the repository root.
 * Version date is fetched from the backend for single source of truth.
 */
export function TermsOfService(): ReactNode {
  const { versions, isLoading, formatVersionDate } = usePolicyVersions()

  const versionDisplay = isLoading
    ? 'Loading...'
    : versions
      ? formatVersionDate(versions.terms_of_service_version)
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

        <h1 className="text-4xl font-bold text-gray-900 mb-2">Terms of Service</h1>
        <p className="text-sm text-gray-600 mb-8">Last Updated: {versionDisplay}</p>

        <div className="prose prose-blue max-w-none space-y-6">
          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Agreement to Terms</h2>
            <p className="text-gray-700 leading-relaxed">
              By accessing or using Tiddly ("the Service"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, do not use the Service.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">About the Service</h2>
            <p className="text-gray-700 leading-relaxed">
              Tiddly is a bookmark management application operated by <strong>Shane Kercheval</strong> as an individual (not a corporation or LLC). The Service allows you to save, organize, and search bookmarks with features including tagging, full-text search, and API access.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Beta Status</h2>
            <div className="bg-yellow-50 border-l-4 border-yellow-400 p-6 my-6">
              <p className="text-gray-900 font-semibold mb-3">The Service is currently in <strong>beta</strong>. This means:</p>
              <ul className="list-disc list-inside space-y-2 text-gray-700">
                <li><strong>No guarantees:</strong> We do not guarantee the accuracy, integrity, or security of your data</li>
                <li><strong>Data loss possible:</strong> Your data may be lost, corrupted, or become inaccessible at any time</li>
                <li><strong>Security limitations:</strong> While we implement security best practices, we cannot guarantee complete security</li>
                <li><strong>No backups guaranteed:</strong> We do not guarantee regular backups or data recovery</li>
                <li><strong>Use at your own risk:</strong> You should maintain your own backups of important data</li>
                <li><strong>Features may change:</strong> Features, APIs, and functionality may change without notice</li>
                <li><strong>Downtime expected:</strong> The Service may experience downtime or become unavailable</li>
                <li><strong>Pricing changes:</strong> Pricing may be introduced in the future</li>
                <li><strong>Termination rights:</strong> We may terminate the Service or your account at any time</li>
              </ul>
              <p className="text-gray-700 mt-4">
                By using the beta Service, you acknowledge and accept these risks.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Acceptable Use</h2>
            <p className="text-gray-700 leading-relaxed mb-3">You agree <strong>NOT</strong> to:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>Use the Service for any illegal purpose</li>
              <li>Store illegal, harmful, or offensive content</li>
              <li>Attempt to hack, disrupt, or overload the Service</li>
              <li>Use the Service to spam or harass others</li>
              <li>Violate any applicable laws or regulations</li>
              <li>Scrape or abuse the Service's resources</li>
              <li>Store malware, viruses, or malicious content</li>
              <li>Use the Service in a way that infringes others' rights</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Your Content</h2>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Ownership</h3>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>You retain all rights to the content you store (bookmarks, notes, etc.)</li>
              <li>You grant us a license to store and display your content to provide the Service</li>
              <li>This license ends when you delete your content or account</li>
            </ul>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Responsibility</h3>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>You are solely responsible for your content</li>
              <li>You represent that you have the right to store and share your content</li>
              <li>We are not responsible for any content you store</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Disclaimers and Limitations of Liability</h2>

            <div className="bg-red-50 border-l-4 border-red-400 p-6 my-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-3">AS-IS SERVICE</h3>
              <p className="text-gray-700 leading-relaxed mb-3">
                THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO:
              </p>
              <ul className="list-disc list-inside space-y-1 text-gray-700">
                <li>Warranties of merchantability</li>
                <li>Fitness for a particular purpose</li>
                <li>Non-infringement</li>
                <li>Reliability, availability, or accuracy</li>
              </ul>

              <h3 className="text-lg font-semibold text-gray-900 mt-6 mb-3">NO LIABILITY</h3>
              <p className="text-gray-700 leading-relaxed mb-3">
                TO THE MAXIMUM EXTENT PERMITTED BY LAW, SHANE KERCHEVAL (THE OPERATOR) SHALL NOT BE LIABLE FOR:
              </p>
              <ul className="list-disc list-inside space-y-1 text-gray-700">
                <li>Loss of data or bookmarks</li>
                <li>Service interruptions or downtime</li>
                <li>Security breaches or unauthorized access</li>
                <li>Any indirect, incidental, special, or consequential damages</li>
                <li>Any damages exceeding $100 USD</li>
              </ul>

              <p className="text-gray-700 mt-4 font-semibold">
                Your sole remedy for dissatisfaction with the Service is to stop using it and delete your account.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Data Backup</h2>
            <div className="bg-orange-50 border-l-4 border-orange-400 p-6 my-6">
              <p className="text-gray-900 font-semibold mb-2">CRITICAL:</p>
              <p className="text-gray-700 leading-relaxed">
                You are responsible for backing up your data. We make no guarantees about data retention or backup. The Service is in beta and data loss may occur.
              </p>
              <p className="text-gray-700 leading-relaxed mt-3">
                <strong>Recommendation:</strong> Regularly export your bookmarks using the API or by self-hosting.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Dispute Resolution</h2>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Governing Law</h3>
            <p className="text-gray-700 leading-relaxed">
              These Terms are governed by the laws of Washington State, USA, without regard to conflict of law principles.
            </p>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Informal Resolution</h3>
            <p className="text-gray-700 leading-relaxed">
              Before filing a claim, you agree to contact us to attempt to resolve the dispute informally.
            </p>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">Arbitration</h3>
            <p className="text-gray-700 leading-relaxed">
              Any disputes that cannot be resolved informally shall be resolved through binding arbitration in Washington State, rather than in court.
            </p>

            <h3 className="text-xl font-semibold text-gray-800 mt-6 mb-3">No Class Actions</h3>
            <p className="text-gray-700 leading-relaxed">
              You agree to resolve disputes individually, not as part of a class action or consolidated proceeding.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">Contact</h2>
            <div className="bg-gray-50 p-6 rounded-lg">
              <p className="text-gray-700 font-semibold">Shane Kercheval</p>
              <p className="text-gray-700">Email: <a href="mailto:shane_kercheval@hotmail.com" className="text-blue-600 hover:underline">shane_kercheval@hotmail.com</a></p>
              <p className="text-gray-700">GitHub: <a href="https://github.com/shanekercheval/bookmarks" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">github.com/shanekercheval/bookmarks</a></p>
            </div>
          </section>

          <section className="mt-12 pt-8 border-t border-gray-200">
            <p className="text-sm text-gray-600 italic">
              <strong>By using Tiddly, you acknowledge that you have read, understood, and agree to be bound by these Terms of Service.</strong>
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
