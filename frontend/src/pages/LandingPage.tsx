import { useAuth0 } from '@auth0/auth0-react'
import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { isDevMode } from '../config'
import { BookmarkIcon } from '../components/icons'
import { Footer } from '../components/Footer'
import { LoadingSpinnerCentered } from '../components/ui'

/**
 * Landing page content shown to unauthenticated users.
 */
function LandingContent({ onLogin }: { onLogin: () => void }): ReactNode {
  return (
    <div className="min-h-screen bg-white">
      {/* Hero Section */}
      <div className="mx-auto max-w-6xl px-6 pb-24 pt-24 sm:px-8 lg:px-12">
        <div className="text-center">
          <div className="mb-8 flex items-center justify-center gap-4">
            <h1 className="text-7xl font-bold tracking-tight text-gray-900 sm:text-8xl">
              Tiddly
            </h1>
            <span className="mb-2 self-start rounded-full border-2 border-orange-200 bg-orange-50 px-4 py-1.5 text-sm font-semibold uppercase tracking-wide text-orange-700">
              Beta
            </span>
          </div>
          <p className="mx-auto mb-4 max-w-3xl text-2xl leading-relaxed text-gray-600">
            Your personal knowledge base. Save and organize content with tags, search, and AI integration.
          </p>
          <p className="mx-auto mb-16 text-base text-gray-500">
            Currently in beta. Things may change as we improve the platform.
          </p>
          <button
            onClick={onLogin}
            className="rounded-full bg-gray-900 px-10 py-4 text-lg font-medium text-white transition-all hover:bg-gray-800 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2"
          >
            Get Started
          </button>
        </div>

        {/* Product Roadmap */}
        <div className="mx-auto mt-32 max-w-4xl">
          <div className="space-y-6">
            {/* Bookmarks - Available Now */}
            <div className="flex items-start gap-6 rounded-2xl bg-gray-50 p-8 transition-all hover:bg-gray-100">
              <div className="flex-shrink-0">
                <BookmarkIcon className="h-10 w-10 text-gray-900" />
              </div>
              <div className="flex-1">
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-3xl font-bold text-gray-900">Bookmarks</h2>
                  <span className="rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">
                    Available Now
                  </span>
                </div>
                <p className="mb-4 text-lg leading-relaxed text-gray-600">
                  Full-text search, flexible tagging, and custom lists.
                  Generate API tokens for CLI access or connect via MCP for AI-powered
                  organization.
                </p>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-lg bg-white px-3 py-1.5 text-sm text-gray-700">
                    Full-text search
                  </span>
                  <span className="rounded-lg bg-white px-3 py-1.5 text-sm text-gray-700">
                    Tags & lists
                  </span>
                  <span className="rounded-lg bg-white px-3 py-1.5 text-sm text-gray-700">
                    API access
                  </span>
                  <span className="rounded-lg bg-white px-3 py-1.5 text-sm text-gray-700">
                    MCP integration
                  </span>
                </div>
              </div>
            </div>

            {/* Notes - Coming Soon */}
            <div className="flex items-start gap-6 rounded-2xl border-2 border-dashed border-gray-200 bg-white p-8 opacity-60">
              <div className="flex-shrink-0">
                <svg
                  className="h-10 w-10 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
              <div className="flex-1">
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-3xl font-bold text-gray-900">Notes</h2>
                  <span className="rounded-full bg-gray-100 px-3 py-1 text-sm font-medium text-gray-600">
                    Coming Soon
                  </span>
                </div>
                <p className="text-lg leading-relaxed text-gray-600">
                  Capture thoughts, ideas, and research. Markdown support, linking between
                  notes and bookmarks, and the same powerful search you love.
                </p>
              </div>
            </div>

            {/* Todos - Coming Soon */}
            <div className="flex items-start gap-6 rounded-2xl border-2 border-dashed border-gray-200 bg-white p-8 opacity-60">
              <div className="flex-shrink-0">
                <svg
                  className="h-10 w-10 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
                  />
                </svg>
              </div>
              <div className="flex-1">
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="text-3xl font-bold text-gray-900">Todos</h2>
                  <span className="rounded-full bg-gray-100 px-3 py-1 text-sm font-medium text-gray-600">
                    Coming Soon
                  </span>
                </div>
                <p className="text-lg leading-relaxed text-gray-600">
                  Manage tasks and projects. Link todos to bookmarks and notes. Everything in
                  one place, organized your way.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Key Features */}
        <div className="mx-auto mt-32 max-w-4xl">
          <h2 className="mb-12 text-center text-4xl font-bold text-gray-900">
            Simple, yet powerful
          </h2>
          <div className="grid gap-8 sm:grid-cols-2">
            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                Search everything
              </h3>
              <p className="text-gray-600">
                Full-text search across titles, URLs, and page content. Find what you need in
                seconds, not minutes.
              </p>
            </div>
            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                Keyboard-first workflow
              </h3>
              <p className="text-gray-600">
                Navigate, search, and organize efficiently with keyboard shortcuts.
                Press <kbd className="rounded bg-gray-100 px-2 py-1 text-sm">/</kbd> to start
                searching.
              </p>
            </div>
            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">API & CLI ready</h3>
              <p className="text-gray-600">
                Generate Personal Access Tokens and integrate with your tools. Automate
                bookmark creation, search from the command line, or build custom workflows.
              </p>
            </div>
            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                AI-powered with MCP
              </h3>
              <p className="text-gray-600">
                Connect Claude and other AI agents via Model Context Protocol. Let AI help you
                organize, search, and make sense of your saved content.
              </p>
            </div>
          </div>
        </div>

        {/* FAQ Section */}
        <div className="mx-auto mt-32 max-w-4xl">
          <h2 className="mb-12 text-center text-4xl font-bold text-gray-900">
            Frequently Asked Questions
          </h2>
          <div className="space-y-8">
            {/* FAQ Item */}
            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                How is my data stored and secured?
              </h3>
              <p className="mb-3 text-gray-600">
                Your data is stored in a PostgreSQL database with encryption at rest enabled by
                default. This protects against physical disk access - if someone stole the
                storage hardware, they couldn't read the data. We use Auth0 for authentication
                and implement multi-tenant architecture to ensure complete data isolation between
                users.
              </p>
              <p className="mb-3 text-gray-600">
                We don't use client-side encryption (end-to-end encryption) because it would
                prevent full-text search across your bookmarks, notes, and todos. Search
                functionality requires the server to be able to read and index your content.
              </p>
              <p className="mb-3 text-gray-600">
                <strong>Important:</strong> As with most web applications, the database
                administrator (me) could technically access your data through normal database
                queries. Encryption at rest doesn't prevent admin access. I have no intention of
                accessing user data and will never do so unless legally required. If you need
                complete privacy where no one else can read your data, consider{' '}
                <a href="#self-host" className="text-blue-600 hover:underline">
                  self-hosting
                </a>
                .
              </p>
              <p className="text-gray-600">
                <strong>Future AI features:</strong> In future versions, we plan to offer
                optional AI-powered features (summarization, auto-suggestions, enhanced search)
                that may send your content to third-party AI services (OpenAI, Anthropic). This
                functionality is not yet implemented and will be completely opt-in and
                configurable when available.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                Who can access my bookmarks?
              </h3>
              <p className="text-gray-600">
                Only you. Your bookmarks are completely private and isolated to your account. We
                use a multi-tenant database architecture where every bookmark is tied to your
                user ID. There's no sharing functionality currently - your data is yours alone.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                What data do you store about my bookmarks?
              </h3>
              <p className="text-gray-600">
                We store the URL, title, description, and page content (up to 500KB per
                bookmark) to enable full-text search. Page content is automatically extracted
                when you save a bookmark. We also track when bookmarks were created, updated,
                and last accessed. All stored data is used solely to provide search and
                organization features.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                What happens to deleted bookmarks?
              </h3>
              <p className="text-gray-600">
                Deleted bookmarks go to your Trash where they can be restored. Currently, we
                don't automatically permanently delete trashed items - they remain in your trash
                until you manually restore or permanently delete them. In a future version, items
                in trash will be automatically permanently deleted after 30 days.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                What are Personal Access Tokens (PATs)?
              </h3>
              <p className="text-gray-600">
                PATs let you access the API programmatically for automation, CLI tools, or custom
                integrations. You can generate tokens in the Settings page. Tokens are stored
                securely (hashed) and prefixed with{' '}
                <code className="rounded bg-gray-100 px-1.5 py-0.5 text-sm">bm_</code>. Use them
                with the Authorization header to access the full REST API.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                What is MCP integration?
              </h3>
              <p className="text-gray-600">
                MCP (Model Context Protocol) allows AI agents like Claude to interact with your
                bookmarks. You can connect Claude Desktop or other MCP-compatible tools to
                search, create, and organize bookmarks using natural language. It requires a
                Personal Access Token for authentication.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                Can I export my data?
              </h3>
              <p className="text-gray-600">
                Not yet through the UI, but you can use the REST API with a Personal Access Token
                to export all your bookmarks programmatically. A built-in export feature is
                planned for a future update.
              </p>
            </div>

            <div>
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                Will this always be free?
              </h3>
              <p className="text-gray-600">
                Tiddly is currently free during beta as we develop features and determine the
                best pricing model. We're committed to transparency - any pricing changes will be
                announced well in advance, and existing users may be grandfathered or given ample
                notice.
              </p>
            </div>

            <div id="self-host">
              <h3 className="mb-3 text-xl font-semibold text-gray-900">
                Can I self-host Tiddly?
              </h3>
              <p className="text-gray-600">
                Yes! The{' '}
                <a
                  href="https://github.com/shane-kercheval/bookmarks"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  codebase is available
                </a>{' '}
                and can be self-hosted. You'll need PostgreSQL, and optionally Auth0 for
                authentication (or use dev mode to bypass auth). Full deployment instructions are
                included in the repository. Self-hosting gives you complete control over your data.
              </p>
            </div>
          </div>
        </div>

        {/* Final CTA */}
        <div className="mt-32 text-center">
          <h2 className="mb-6 text-4xl font-bold text-gray-900">Start organizing today</h2>
          <p className="mb-10 text-xl text-gray-600">
            Free while in beta. Pricing to be determined.
          </p>
          <button
            onClick={onLogin}
            className="rounded-full bg-gray-900 px-10 py-4 text-lg font-medium text-white transition-all hover:bg-gray-800 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-gray-900 focus:ring-offset-2"
          >
            Get Started
          </button>
        </div>

      </div>
      <Footer />
    </div>
  )
}

/**
 * Landing page with Auth0 authentication (production mode).
 */
function AuthenticatedLandingPage(): ReactNode {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0()

  if (isLoading) {
    return <LoadingSpinnerCentered />
  }

  // If already authenticated, redirect to app
  if (isAuthenticated) {
    return <Navigate to="/app/bookmarks" replace />
  }

  return <LandingContent onLogin={() => loginWithRedirect()} />
}

/**
 * Landing page component - public entry point.
 * In dev mode, redirects directly to app.
 * In production, shows login button for unauthenticated users.
 */
export function LandingPage(): ReactNode {
  // In dev mode, go straight to app
  if (isDevMode) {
    return <Navigate to="/app/bookmarks" replace />
  }

  return <AuthenticatedLandingPage />
}
