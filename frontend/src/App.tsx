import { lazy, Suspense } from 'react'
import { createBrowserRouter, RouterProvider, Navigate, Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './components/AuthProvider'
import { SessionExpiryGuard } from './components/SessionExpiredDialog'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AppLayout } from './components/AppLayout'
import { Layout } from './components/Layout'
import { LandingPage } from './pages/LandingPage'
import { AccountDeleted } from './pages/AccountDeleted'
import { AllContent } from './pages/AllContent'
import { LoadingSpinnerPage } from './components/ui'

// Lazy-loaded routes — keep in sync with routePrefetch.ts
// Lazy-loaded layouts (only used by lazy routes)
const DocsLayout = lazy(() => import('./components/DocsLayout').then(m => ({ default: m.DocsLayout })))
const PublicPageLayout = lazy(() => import('./components/PublicPageLayout').then(m => ({ default: m.PublicPageLayout })))
const PublicSharedTocLayout = lazy(() => import('./components/PublicPageLayout').then(m => ({ default: m.PublicSharedTocLayout })))

// Lazy-loaded detail pages (heavy — pulls in CodeMirror + Milkdown)
const BookmarkDetail = lazy(() => import('./pages/BookmarkDetail').then(m => ({ default: m.BookmarkDetail })))
const NoteDetail = lazy(() => import('./pages/NoteDetail').then(m => ({ default: m.NoteDetail })))
const PromptDetail = lazy(() => import('./pages/PromptDetail').then(m => ({ default: m.PromptDetail })))

// Lazy-loaded public read-only views (reuse the detail render components in readOnly mode)
const PublicBookmark = lazy(() => import('./pages/PublicBookmark').then(m => ({ default: m.PublicBookmark })))
const PublicNote = lazy(() => import('./pages/PublicNote').then(m => ({ default: m.PublicNote })))
const PublicPrompt = lazy(() => import('./pages/PublicPrompt').then(m => ({ default: m.PublicPrompt })))
const SaveSharedRedirect = lazy(() => import('./pages/SaveSharedRedirect').then(m => ({ default: m.SaveSharedRedirect })))

// Lazy-loaded settings pages
const SettingsGeneral = lazy(() => import('./pages/settings/SettingsGeneral').then(m => ({ default: m.SettingsGeneral })))
const SettingsAccount = lazy(() => import('./pages/settings/SettingsAccount').then(m => ({ default: m.SettingsAccount })))
const SettingsTokens = lazy(() => import('./pages/settings/SettingsTokens').then(m => ({ default: m.SettingsTokens })))
const SettingsAI = lazy(() => import('./pages/settings/SettingsAI').then(m => ({ default: m.SettingsAI })))
const SettingsMCP = lazy(() => import('./pages/settings/SettingsMCP').then(m => ({ default: m.SettingsMCP })))
const SettingsTags = lazy(() => import('./pages/settings/SettingsTags').then(m => ({ default: m.SettingsTags })))
const SettingsFAQ = lazy(() => import('./pages/settings/SettingsFAQ').then(m => ({ default: m.SettingsFAQ })))
const SettingsVersionHistory = lazy(() => import('./pages/settings/SettingsVersionHistory').then(m => ({ default: m.SettingsVersionHistory })))
const SettingsSharedContent = lazy(() => import('./pages/settings/SettingsSharedContent').then(m => ({ default: m.SettingsSharedContent })))

// Lazy-loaded docs pages
const DocsOverview = lazy(() => import('./pages/docs/DocsOverview').then(m => ({ default: m.DocsOverview })))
const DocsAIHub = lazy(() => import('./pages/docs/DocsAIHub').then(m => ({ default: m.DocsAIHub })))
const DocsCLIHub = lazy(() => import('./pages/docs/DocsCLIHub').then(m => ({ default: m.DocsCLIHub })))
const DocsCLIReference = lazy(() => import('./pages/docs/DocsCLIReference').then(m => ({ default: m.DocsCLIReference })))
const DocsCLIMCP = lazy(() => import('./pages/docs/DocsCLIMCP').then(m => ({ default: m.DocsCLIMCP })))
const DocsCLISkills = lazy(() => import('./pages/docs/DocsCLISkills').then(m => ({ default: m.DocsCLISkills })))
const DocsExtensionsHub = lazy(() => import('./pages/docs/DocsExtensionsHub').then(m => ({ default: m.DocsExtensionsHub })))
const DocsExtensionsChrome = lazy(() => import('./pages/docs/DocsExtensionsChrome').then(m => ({ default: m.DocsExtensionsChrome })))
const DocsExtensionsSafari = lazy(() => import('./pages/docs/DocsExtensionsSafari').then(m => ({ default: m.DocsExtensionsSafari })))
const DocsAPI = lazy(() => import('./pages/docs/DocsAPI').then(m => ({ default: m.DocsAPI })))
const DocsFeaturesHub = lazy(() => import('./pages/docs/DocsFeaturesHub').then(m => ({ default: m.DocsFeaturesHub })))
const DocsContentTypes = lazy(() => import('./pages/docs/DocsContentTypes').then(m => ({ default: m.DocsContentTypes })))
const DocsPrompts = lazy(() => import('./pages/docs/DocsPrompts').then(m => ({ default: m.DocsPrompts })))
const DocsTagsFilters = lazy(() => import('./pages/docs/DocsTagsFilters').then(m => ({ default: m.DocsTagsFilters })))
const DocsSearch = lazy(() => import('./pages/docs/DocsSearch').then(m => ({ default: m.DocsSearch })))
const DocsVersioning = lazy(() => import('./pages/docs/DocsVersioning').then(m => ({ default: m.DocsVersioning })))
const DocsShortcuts = lazy(() => import('./pages/docs/DocsShortcuts').then(m => ({ default: m.DocsShortcuts })))
const DocsAIFeatures = lazy(() => import('./pages/docs/DocsAIFeatures').then(m => ({ default: m.DocsAIFeatures })))
const DocsFAQ = lazy(() => import('./pages/docs/DocsFAQ').then(m => ({ default: m.DocsFAQ })))
const DocsKnownIssues = lazy(() => import('./pages/docs/DocsKnownIssues').then(m => ({ default: m.DocsKnownIssues })))
const DocsTips = lazy(() => import('./pages/docs/DocsTips').then(m => ({ default: m.DocsTips })))

// Lazy-loaded public pages
const FeaturesPage = lazy(() => import('./pages/FeaturesPage').then(m => ({ default: m.FeaturesPage })))
const Pricing = lazy(() => import('./pages/Pricing').then(m => ({ default: m.Pricing })))
const PrivacyPolicy = lazy(() => import('./pages/PrivacyPolicy').then(m => ({ default: m.PrivacyPolicy })))
const TermsOfService = lazy(() => import('./pages/TermsOfService').then(m => ({ default: m.TermsOfService })))
const Changelog = lazy(() => import('./pages/changelog/Changelog').then(m => ({ default: m.Changelog })))
const Roadmap = lazy(() => import('./pages/roadmap/Roadmap').then(m => ({ default: m.Roadmap })))

/**
 * Root layout component that wraps the entire app with providers.
 */
function RootLayout(): ReactNode {
  return (
    <AuthProvider>
      <Toaster position="top-right" />
      <SessionExpiryGuard />
      <Suspense fallback={<LoadingSpinnerPage />}>
        <Outlet />
      </Suspense>
    </AuthProvider>
  )
}

/**
 * Router configuration using createBrowserRouter for data router features.
 * This enables useBlocker and other data router hooks.
 */
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      // Public routes
      { path: '/', element: <LandingPage /> },
      { path: '/features', element: <FeaturesPage /> },
      { path: '/privacy', element: <PrivacyPolicy /> },
      { path: '/terms', element: <TermsOfService /> },
      // Terminal screen after account deletion (signed-out; no re-auth path).
      { path: '/account-deleted', element: <AccountDeleted /> },

      // Public docs routes
      {
        element: <DocsLayout />,
        children: [
          { path: '/docs', element: <DocsOverview /> },
          { path: '/docs/features', element: <DocsFeaturesHub /> },
          { path: '/docs/features/content-types', element: <DocsContentTypes /> },
          { path: '/docs/features/prompts', element: <DocsPrompts /> },
          { path: '/docs/features/tags-filters', element: <DocsTagsFilters /> },
          { path: '/docs/features/search', element: <DocsSearch /> },
          { path: '/docs/features/versioning', element: <DocsVersioning /> },
          { path: '/docs/features/shortcuts', element: <DocsShortcuts /> },
          { path: '/docs/features/ai', element: <DocsAIFeatures /> },
          { path: '/docs/ai', element: <DocsAIHub /> },
          { path: '/docs/cli', element: <DocsCLIHub /> },
          { path: '/docs/cli/mcp', element: <DocsCLIMCP /> },
          { path: '/docs/cli/skills', element: <DocsCLISkills /> },
          { path: '/docs/cli/reference', element: <DocsCLIReference /> },
          { path: '/docs/extensions', element: <DocsExtensionsHub /> },
          { path: '/docs/extensions/chrome', element: <DocsExtensionsChrome /> },
          { path: '/docs/extensions/safari', element: <DocsExtensionsSafari /> },
          { path: '/docs/api', element: <DocsAPI /> },
          { path: '/docs/tips', element: <DocsTips /> },
          { path: '/docs/faq', element: <DocsFAQ /> },
          { path: '/docs/known-issues', element: <DocsKnownIssues /> },
        ],
      },

      // Top-level public routes with shared header/footer. Chrome is
      // single-sourced; the content area splits into the standard centered
      // layout and the ToC-capable shared-item layout (see PublicPageLayout).
      {
        element: <PublicPageLayout />,
        children: [
          { path: '/changelog', element: <Changelog /> },
          { path: '/roadmap', element: <Roadmap /> },
          { path: '/pricing', element: <Pricing /> },
          // Shared bookmarks are deliberately ToC-less (scraped content has no
          // headings), so they use the standard layout — the sidebar margin
          // structurally cannot apply to them.
          { path: '/shared/bookmarks/:token', element: <PublicBookmark /> },
        ],
      },
      // Public read-only share views with ToC support (no auth). The render
      // components run in readOnly mode; the only action is the auth-aware
      // "Save a copy".
      {
        element: <PublicSharedTocLayout />,
        children: [
          { path: '/shared/notes/:token', element: <PublicNote /> },
          { path: '/shared/prompts/:token', element: <PublicPrompt /> },
        ],
      },

      // Protected app routes - requires auth
      {
        element: <ProtectedRoute />,
        children: [
          {
            element: <AppLayout />,
            children: [
              // In-app save target for the public "Save to Tiddly" flow.
              // Sibling of Layout (not a child) so it renders without the app
              // shell's sidebar/filters/tags fetches.
              { path: '/app/save-shared/:type/:token', element: <SaveSharedRedirect /> },
              {
                element: <Layout />,
                children: [
                  // /app root redirects to content
                  { path: '/app', element: <Navigate to="/app/content" replace /> },

                  // Unified content routes (All, Archived, Trash, Filters)
                  { path: '/app/content', element: <AllContent /> },
                  { path: '/app/content/archived', element: <AllContent /> },
                  { path: '/app/content/trash', element: <AllContent /> },
                  { path: '/app/content/filters/:filterId', element: <AllContent /> },

                  // Bookmark detail routes
                  { path: '/app/bookmarks/new', element: <BookmarkDetail /> },
                  { path: '/app/bookmarks/:id', element: <BookmarkDetail /> },

                  // Single route handles both create (id="new") and edit (id=UUID).
                  // This is intentional — separate routes cause React Router to unmount/remount
                  // the component when navigating from /new to /:id, destroying editor state.
                  { path: '/app/notes/:id', element: <NoteDetail /> },

                  // Single route for prompts — same reason as notes above.
                  { path: '/app/prompts/:id', element: <PromptDetail /> },

                  // Settings routes
                  { path: '/app/settings', element: <Navigate to="/app/settings/general" replace /> },
                  { path: '/app/settings/general', element: <SettingsGeneral /> },
                  { path: '/app/settings/account', element: <SettingsAccount /> },
                  { path: '/app/settings/tokens', element: <SettingsTokens /> },
                  { path: '/app/settings/ai', element: <SettingsAI /> },
                  { path: '/app/settings/ai-integration', element: <SettingsMCP /> },
                  { path: '/app/settings/tags', element: <SettingsTags /> },
                  { path: '/app/settings/history', element: <SettingsVersionHistory /> },
                  { path: '/app/settings/shared', element: <SettingsSharedContent /> },
                  { path: '/app/settings/faq', element: <SettingsFAQ /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
])

/**
 * Main application component with routing configuration.
 *
 * Route structure:
 * - Public routes (no auth required):
 *   - / : Landing page
 *   - /privacy : Privacy Policy
 *   - /terms : Terms of Service
 *   - /docs/* : Documentation pages
 *   - /changelog : Changelog
 *   - /roadmap : Roadmap
 *
 * - App routes (authentication required):
 *   - /app : Redirects to /app/content
 *   - /app/save-shared/:type/:token : Save-a-copy target for the public share flow
 *   - /app/content : Unified view - all content (bookmarks + notes + prompts)
 *   - /app/content/archived : Archived content
 *   - /app/content/trash : Deleted content
 *   - /app/content/filters/:filterId : Custom filter
 *   - /app/bookmarks/new : Create new bookmark
 *   - /app/bookmarks/:id : View/edit bookmark (unified component)
 *   - /app/notes/new : Create new note
 *   - /app/notes/:id : View/edit note (unified component)
 *   - /app/prompts/new : Create new prompt
 *   - /app/prompts/:id : View/edit prompt (unified component)
 *   - /app/settings : Redirects to /app/settings/general
 *   - /app/settings/general : General UI preferences
 *   - /app/settings/tokens : Personal access tokens
 *   - /app/settings/ai : AI configuration (BYOK key, model selection)
 *   - /app/settings/ai-integration : MCP integration setup
 *   - /app/settings/tags : Tag management
 *   - /app/settings/faq : Frequently asked questions
 */
function App(): ReactNode {
  return <RouterProvider router={router} />
}

export default App
