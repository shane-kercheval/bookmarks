import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './components/AuthProvider'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { LandingPage } from './pages/LandingPage'
import { Bookmarks } from './pages/Bookmarks'
import { SettingsGeneral } from './pages/settings/SettingsGeneral'
import { SettingsTokens } from './pages/settings/SettingsTokens'
import { SettingsMCP } from './pages/settings/SettingsMCP'
import { SettingsBookmarks } from './pages/settings/SettingsBookmarks'
import { SettingsTags } from './pages/settings/SettingsTags'

/**
 * Main application component with routing configuration.
 *
 * Routes:
 * - / : Landing page (public)
 * - /bookmarks : All bookmarks (protected)
 * - /bookmarks/archived : Archived bookmarks (protected)
 * - /bookmarks/trash : Trash (protected)
 * - /bookmarks/lists/:listId : Custom list (protected)
 * - /settings/general : General UI preferences (protected)
 * - /settings/tokens : Personal access tokens (protected)
 * - /settings/mcp : MCP integration setup (protected)
 * - /settings/bookmarks : Bookmark lists and tab order (protected)
 * - /settings/tags : Tag management (protected)
 */
function App(): ReactNode {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              {/* Bookmarks routes */}
              <Route path="/bookmarks" element={<Bookmarks />} />
              <Route path="/bookmarks/archived" element={<Bookmarks />} />
              <Route path="/bookmarks/trash" element={<Bookmarks />} />
              <Route path="/bookmarks/lists/:listId" element={<Bookmarks />} />

              {/* Settings routes */}
              <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
              <Route path="/settings/general" element={<SettingsGeneral />} />
              <Route path="/settings/tokens" element={<SettingsTokens />} />
              <Route path="/settings/mcp" element={<SettingsMCP />} />
              <Route path="/settings/bookmarks" element={<SettingsBookmarks />} />
              <Route path="/settings/tags" element={<SettingsTags />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
