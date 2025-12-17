import { Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Sidebar } from './sidebar'

/**
 * Layout component that wraps authenticated pages.
 * Includes sidebar with navigation and user controls.
 */
export function Layout(): ReactNode {
  return (
    <div className="flex min-h-screen bg-white">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <div className="max-w-5xl px-6 py-8 md:px-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
