import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './components/AuthProvider'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AppLayout } from './components/AppLayout'
import { Layout } from './components/Layout'
import { LandingPage } from './pages/LandingPage'
import { PrivacyPolicy } from './pages/PrivacyPolicy'
import { TermsOfService } from './pages/TermsOfService'
import { Bookmarks } from './pages/Bookmarks'
import { Notes } from './pages/Notes'
import { NoteDetail } from './pages/NoteDetail'
import { AllContent } from './pages/AllContent'
import { SettingsGeneral } from './pages/settings/SettingsGeneral'
import { SettingsTokens } from './pages/settings/SettingsTokens'
import { SettingsMCP } from './pages/settings/SettingsMCP'
import { SettingsLists } from './pages/settings/SettingsLists'
import { SettingsTags } from './pages/settings/SettingsTags'

/**
 * Main application component with routing configuration.
 *
 * Route structure:
 * - Public routes (no auth required):
 *   - / : Landing page
 *   - /privacy : Privacy Policy
 *   - /terms : Terms of Service
 *
 * - App routes (authentication + consent required):
 *   - /app : App container (redirects to /app/bookmarks)
 *   - /app/content : Unified view - all content (bookmarks + notes)
 *   - /app/content/archived : Unified view - archived content
 *   - /app/content/trash : Unified view - deleted content
 *   - /app/content/lists/:listId : Custom shared list (mixed types)
 *   - /app/bookmarks : All bookmarks
 *   - /app/bookmarks/archived : Archived bookmarks
 *   - /app/bookmarks/trash : Trash
 *   - /app/bookmarks/lists/:listId : Custom list
 *   - /app/notes : All notes
 *   - /app/notes/new : Create new note
 *   - /app/notes/archived : Archived notes
 *   - /app/notes/trash : Trash
 *   - /app/notes/lists/:listId : Custom list
 *   - /app/notes/:id : View note
 *   - /app/notes/:id/edit : Edit note
 *   - /app/settings : Redirects to /app/settings/general
 *   - /app/settings/general : General UI preferences
 *   - /app/settings/tokens : Personal access tokens
 *   - /app/settings/mcp : MCP integration setup
 *   - /app/settings/lists : Content lists and tab order
 *   - /app/settings/tags : Tag management
 *
 * - Legacy redirects (backward compatibility):
 *   - /bookmarks : Redirects to /app/bookmarks
 *   - /settings : Redirects to /app/settings
 */
function App(): ReactNode {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/privacy" element={<PrivacyPolicy />} />
          <Route path="/terms" element={<TermsOfService />} />

          {/* Legacy redirects for backward compatibility */}
          <Route path="/bookmarks" element={<Navigate to="/app/bookmarks" replace />} />
          <Route path="/bookmarks/*" element={<Navigate to="/app/bookmarks" replace />} />
          <Route path="/settings" element={<Navigate to="/app/settings" replace />} />
          <Route path="/settings/*" element={<Navigate to="/app/settings/general" replace />} />

          {/* Protected app routes - requires auth + consent */}
          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route element={<Layout />}>
                {/* /app root redirects to bookmarks */}
                <Route path="/app" element={<Navigate to="/app/bookmarks" replace />} />

                {/* Unified content routes (shared views: All, Archived, Trash, Lists) */}
                <Route path="/app/content" element={<AllContent />} />
                <Route path="/app/content/archived" element={<AllContent />} />
                <Route path="/app/content/trash" element={<AllContent />} />
                <Route path="/app/content/lists/:listId" element={<AllContent />} />

                {/* Bookmarks routes */}
                <Route path="/app/bookmarks" element={<Bookmarks />} />
                <Route path="/app/bookmarks/archived" element={<Bookmarks />} />
                <Route path="/app/bookmarks/trash" element={<Bookmarks />} />
                <Route path="/app/bookmarks/lists/:listId" element={<Bookmarks />} />

                {/* Notes routes */}
                <Route path="/app/notes" element={<Notes />} />
                <Route path="/app/notes/new" element={<NoteDetail />} />
                <Route path="/app/notes/archived" element={<Notes />} />
                <Route path="/app/notes/trash" element={<Notes />} />
                <Route path="/app/notes/lists/:listId" element={<Notes />} />
                <Route path="/app/notes/:id" element={<NoteDetail />} />
                <Route path="/app/notes/:id/edit" element={<NoteDetail />} />

                {/* Settings routes */}
                <Route path="/app/settings" element={<Navigate to="/app/settings/general" replace />} />
                <Route path="/app/settings/general" element={<SettingsGeneral />} />
                <Route path="/app/settings/tokens" element={<SettingsTokens />} />
                <Route path="/app/settings/mcp" element={<SettingsMCP />} />
                <Route path="/app/settings/lists" element={<SettingsLists />} />
                {/* TODO: Remove this redirect after 2025-06-01 (legacy route support) */}
                <Route path="/app/settings/bookmarks" element={<Navigate to="/app/settings/lists" replace />} />
                <Route path="/app/settings/tags" element={<SettingsTags />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
