import { BrowserRouter, Routes, Route } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './components/AuthProvider'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { LandingPage } from './pages/LandingPage'
import { Bookmarks } from './pages/Bookmarks'

/**
 * Main application component with routing configuration.
 *
 * Routes:
 * - / : Landing page (public)
 * - /bookmarks : Bookmark list (protected)
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
              <Route path="/bookmarks" element={<Bookmarks />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
