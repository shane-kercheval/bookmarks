import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useConsentStore } from '../stores/consentStore'

/**
 * Modal dialog for user consent to Privacy Policy and Terms of Service.
 *
 * Features:
 * - Blocks app access until user explicitly consents
 * - Requires checking a checkbox (affirmative action)
 * - Links to full policy documents open in new tab
 * - Handles loading and error states
 */
export function ConsentDialog(): ReactNode {
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const { isLoading, error, recordConsent } = useConsentStore()

  const handleAccept = async (): Promise<void> => {
    if (!agreedToTerms) return

    try {
      await recordConsent()
      // Dialog will auto-close when needsConsent becomes false
    } catch (err) {
      // Error is already set in store, will be displayed
      console.error('Failed to record consent:', err)
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-900 bg-opacity-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 md:p-8"
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-title"
      >
        <div className="mb-6">
          <h2
            id="consent-title"
            className="text-2xl font-bold text-gray-900 mb-2"
          >
            Welcome to Tiddly
          </h2>
          <p className="text-gray-600">
            Before you continue, please review and accept our policies
          </p>
        </div>

        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-md">
          <p className="text-sm text-gray-700 leading-relaxed">
            By using Tiddly, you agree to our{' '}
            <Link
              to="/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 font-medium underline"
            >
              Privacy Policy
            </Link>{' '}
            and{' '}
            <Link
              to="/terms"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 font-medium underline"
            >
              Terms of Service
            </Link>
            .
          </p>
          <p className="text-sm text-gray-700 mt-3 leading-relaxed">
            We collect and store your content (e.g. bookmarks, notes, todos, etc.), email address, and aggregated usage data to provide the service.
            Tiddly is currently in <span className="font-semibold">beta</span> - data loss is possible.
          </p>
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-700">
              <strong>Error:</strong> {error}
            </p>
          </div>
        )}

        <div className="mb-6">
          <label className="flex items-start cursor-pointer group">
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              className="mt-1 h-5 w-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              disabled={isLoading}
            />
            <span className="ml-3 text-sm text-gray-700 select-none group-hover:text-gray-900">
              I have read and agree to the Privacy Policy and Terms of Service
            </span>
          </label>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            You must accept to use Tiddly
          </p>
          <button
            type="button"
            onClick={handleAccept}
            disabled={!agreedToTerms || isLoading}
            className={`px-6 py-2 rounded-md font-medium transition-colors ${
              agreedToTerms && !isLoading
                ? 'bg-blue-600 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }`}
          >
            {isLoading ? 'Processing...' : 'Accept and Continue'}
          </button>
        </div>

        <div className="mt-6 text-center">
          <p className="text-xs text-gray-500">
            Last Updated: December 20, 2024
          </p>
        </div>
      </div>
    </div>
  )
}
