import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './components/AuthProvider'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { LandingPage } from './pages/LandingPage'
import { Bookmarks } from './pages/Bookmarks'
import { SettingsTokens } from './pages/settings/SettingsTokens'
import { SettingsBookmarks } from './pages/settings/SettingsBookmarks'

/**
 * Main application component with routing configuration.
 *
 * Routes:
 * - / : Landing page (public)
 * - /bookmarks : All bookmarks (protected)
 * - /bookmarks/archived : Archived bookmarks (protected)
 * - /bookmarks/trash : Trash (protected)
 * - /bookmarks/lists/:listId : Custom list (protected)
 * - /settings/tokens : Personal access tokens (protected)
 * - /settings/bookmarks : Bookmark lists and tab order (protected)
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
              <Route path="/settings" element={<Navigate to="/settings/tokens" replace />} />
              <Route path="/settings/tokens" element={<SettingsTokens />} />
              <Route path="/settings/bookmarks" element={<SettingsBookmarks />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
