import { describe, it, expect } from 'vitest'
import { render, screen, type RenderResult } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DocsMarkdown } from './DocsMarkdown'

function renderMarkdown(body: string): RenderResult {
  return render(
    <MemoryRouter>
      <DocsMarkdown body={body} />
    </MemoryRouter>,
  )
}

describe('DocsMarkdown', () => {
  it('keeps headings (docs schema does not strip them)', () => {
    renderMarkdown('# Title\n\n## Section\n\nBody text.')
    expect(screen.getByRole('heading', { level: 1, name: 'Title' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Section' })).toBeInTheDocument()
  })

  it('renders GFM tables', () => {
    renderMarkdown('| A | B |\n| - | - |\n| 1 | 2 |')
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '1' })).toBeInTheDocument()
  })

  it('lowers `> [!variant]` blockquotes to styled callouts', () => {
    const { container } = renderMarkdown('> [!warning]\n> Heads up.')
    const callout = container.querySelector('.callout-warning')
    expect(callout).not.toBeNull()
    expect(callout?.textContent).toContain('Heads up.')
    // The marker itself must not leak into the rendered text.
    expect(callout?.textContent).not.toContain('[!warning]')
  })

  it('renders a normal blockquote when there is no alert marker', () => {
    const { container } = renderMarkdown('> Just a quote.')
    expect(container.querySelector('blockquote')).not.toBeNull()
    expect(container.querySelector('.callout-info')).toBeNull()
  })

  it('accepts the shared grammar: aliases and bang-less markers collapse to docs variants', () => {
    // Grammar lives in utils/callouts.ts (shared across all three markdown
    // pipelines); the five canonical variants map onto the docs' three styles.
    const danger = renderMarkdown('> [!danger]\n> Careful.').container
    expect(danger.querySelector('.callout-warning')).not.toBeNull()

    const bangless = renderMarkdown('> [note]\n> FYI.').container
    expect(bangless.querySelector('.callout-info')).not.toBeNull()

    const important = renderMarkdown('> [!IMPORTANT]\n> Big.').container
    expect(important.querySelector('.callout-info')).not.toBeNull()
  })

  it('drops a hard line-break left behind by marker stripping', () => {
    // `> [!tip]␣␣` (trailing spaces = hard break) parses as [text, break, ...];
    // removing the empty marker text node must also remove the break, or the
    // body starts with a stray blank line.
    const { container } = renderMarkdown('> [!tip]  \n> Body.')
    const callout = container.querySelector('.callout-tip')
    expect(callout).not.toBeNull()
    expect(callout?.querySelector('br')).toBeNull()
    expect(callout?.textContent).toContain('Body.')
  })

  it('renders fenced code with a copy button', () => {
    renderMarkdown('```bash\necho hello\n```')
    expect(screen.getByText('echo hello')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument()
  })

  it('renders internal links as SPA router links with the brand color', () => {
    renderMarkdown('[Settings](/app/settings/tokens)')
    const link = screen.getByRole('link', { name: 'Settings' })
    expect(link).toHaveAttribute('href', '/app/settings/tokens')
    expect(link).not.toHaveAttribute('target')
    expect(link.className).toContain('text-[#d97b3d]')
    // Orange, underline on hover only — not the static underline `prose` adds.
    expect(link.className).toContain('no-underline')
  })

  it('styles inline code as a gray chip', () => {
    const { container } = renderMarkdown('Press `Cmd+V` to paste.')
    const code = container.querySelector('code')
    expect(code?.textContent).toBe('Cmd+V')
    expect(code?.className).toContain('bg-gray-100')
  })

  it('opens external links in a new tab', () => {
    renderMarkdown('[Store](https://example.com)')
    const link = screen.getByRole('link', { name: 'Store' })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('replaces `{{icon:id}}` inline tokens with an icon, not literal text', () => {
    const { container } = renderMarkdown('Click the `{{icon:pin}}` pin icon.')
    expect(container.querySelector('svg')).not.toBeNull()
    expect(container.textContent).not.toContain('{{icon:pin}}')
  })

  it('throws on an unknown icon token so typos fail loudly', () => {
    expect(() => renderMarkdown('`{{icon:nope}}`')).toThrow(/Unknown inline icon token/)
  })

  it('renders `{{shortcut:id}}` inline tokens as a key chip, not literal text', () => {
    const { container } = renderMarkdown('Press `{{shortcut:app.commandPalette}}` to search.')
    expect(container.querySelector('kbd')).not.toBeNull()
    expect(container.textContent).not.toContain('{{shortcut:')
  })

  it('throws on an unknown shortcut token so typos fail loudly', () => {
    expect(() => renderMarkdown('`{{shortcut:not.a.real.id}}`')).toThrow(/Unknown content shortcut id/)
  })

  it('renders an all-bold-led ordered list as step cards', () => {
    const { container } = renderMarkdown('1. **Install**\n\n   Do this.\n\n2. **Configure**\n\n   Then that.')
    expect(container.querySelector('ol.docs-steps')).not.toBeNull()
  })

  it('renders a plain ordered list (no bold titles) as a normal list', () => {
    const { container } = renderMarkdown('1. Open the menu.\n2. Click save.')
    expect(container.querySelector('ol.docs-steps')).toBeNull()
    expect(container.querySelector('ol')).not.toBeNull()
  })
})
