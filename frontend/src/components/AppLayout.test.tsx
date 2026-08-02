/**
 * AppLayout is a pass-through since the consent gate was removed (2026-08-01).
 *
 * This file previously covered the consent check, the blocking dialog, the
 * dev-mode bypass, and the retry-on-error panel — all deleted with the gate.
 * What survives is the one thing the component still does, and the reason it
 * still exists at all: it is a routing level whose child must render. See the
 * component docstring for why collapsing it would change what
 * `/app/save-shared/:type/:token` fetches.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AppLayout } from './AppLayout'

describe('AppLayout', () => {
  it('renders child routes', () => {
    render(
      <MemoryRouter initialEntries={['/app/test']}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/app/test" element={<div data-testid="child-content">Child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByTestId('child-content')).toBeInTheDocument()
  })
})
