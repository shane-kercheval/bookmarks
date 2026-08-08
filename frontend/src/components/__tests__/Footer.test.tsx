/**
 * The footer must size its layout from its OWN width, not the viewport.
 *
 * Wherever it sits in a box narrower than the window — public share pages with
 * the ToC sidebar open, the app's sidebar-offset content column — viewport
 * media queries kept the fixed-height single-row desktop layout active while
 * the links wrapped, clipping them. jsdom evaluates no CSS, so this pins the
 * mechanism (container queries) rather than the rendered geometry.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Footer } from '../Footer'

function renderFooter(): HTMLElement {
  const { container } = render(
    <MemoryRouter>
      <Footer />
    </MemoryRouter>,
  )
  return container.querySelector('footer') as HTMLElement
}

describe('Footer', () => {
  it('renders the legal and repository links', () => {
    renderFooter()
    for (const name of ['Docs', 'Privacy Policy', 'Terms of Service', 'License', 'GitHub']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument()
    }
  })

  it('drives its layout from its own width, not the viewport', () => {
    const footer = renderFooter()

    // Establishes the footer as a query container...
    expect(footer.className).toMatch(/\B@container\b/)
    // ...and no descendant may switch layout on a viewport breakpoint.
    const viewportVariant = /(?:^|\s)(?:sm|md|lg|xl|2xl):(?:flex-|h-|py-|gap-)/
    for (const el of [footer, ...footer.querySelectorAll('*')]) {
      expect(el.className).not.toMatch(viewportVariant)
    }
  })

  it('lets the link row wrap instead of overflowing a narrow box', () => {
    // space-x-* leaves wrapped rows unevenly spaced; gap-x/gap-y is the
    // wrap-safe equivalent.
    const linkRow = renderFooter().querySelector('a')?.parentElement
    expect(linkRow?.className).toMatch(/\bflex-wrap\b/)
    expect(linkRow?.className).not.toMatch(/\bspace-x-/)
  })
})
