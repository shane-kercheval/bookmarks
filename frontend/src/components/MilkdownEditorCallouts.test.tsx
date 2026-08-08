/**
 * Fixture tests for callout rendering in the reading-mode Milkdown preview —
 * asserting against the ACTUAL Milkdown-parsed document, not a mocked shape.
 *
 * This is the architecture gate for the span-scoped decoration design: the
 * canonical multi-line form `> [!WARNING]` + `> body` parses as ONE paragraph
 * (marker and body separated by a soft break), so these tests specifically
 * verify that body text is NOT swept into the marker/title treatment.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { MilkdownEditor } from './MilkdownEditor'
import { markdownStyleExtension } from '../utils/markdownStyleExtension'

async function renderPreview(value: string): Promise<HTMLElement> {
  const { container } = render(<MilkdownEditor value={value} onChange={() => {}} readOnly={true} />)
  await waitFor(() => expect(container.querySelector('.ProseMirror')).toBeTruthy())
  return container
}

describe('MilkdownEditor — callout rendering (reading mode)', () => {
  it('canonical soft-break form: marker isolated, body keeps body styling', async () => {
    const container = await renderPreview('> [!WARNING]\n> Body text here')

    const blockquote = container.querySelector('blockquote')
    expect(blockquote?.classList.contains('callout')).toBe(true)
    expect(blockquote?.classList.contains('callout-warning')).toBe(true)

    // The marker span covers exactly the raw marker (CSS hides it and renders
    // icon + label in its place)...
    const marker = container.querySelector('.callout-marker')
    expect(marker?.textContent).toBe('[!WARNING]')
    expect(marker?.classList.contains('callout-marker-labeled')).toBe(true)

    // ...and the body — same paragraph, after the soft break — is untouched.
    expect(blockquote?.textContent).toContain('Body text here')
    expect(marker?.textContent).not.toContain('Body')
    expect(container.querySelector('.callout-title')).toBeNull()
  })

  it('custom title: title span styled, marker unlabeled, body untouched', async () => {
    const container = await renderPreview('> [!note] My Title\n> Body text')

    expect(container.querySelector('blockquote')?.classList.contains('callout-note')).toBe(true)
    const title = container.querySelector('.callout-title')
    expect(title?.textContent).toBe('My Title')
    const marker = container.querySelector('.callout-marker')
    // The hidden marker span absorbs the whitespace before the title — a bare
    // text node between the hidden span and the block-displayed title would
    // strand in its own line box and render as a blank line above the title.
    expect(marker?.textContent).toBe('[!note] ')
    expect(title?.previousSibling).toBe(marker)
    expect(marker?.classList.contains('callout-marker-labeled')).toBe(false)
    expect(title?.textContent).not.toContain('Body')
  })

  it('blank-line-separated body (marker in its own paragraph)', async () => {
    const container = await renderPreview('> [!TIP]\n>\n> Body paragraph')

    expect(container.querySelector('blockquote')?.classList.contains('callout-tip')).toBe(true)
    expect(container.querySelector('.callout-marker')?.textContent).toBe('[!TIP]')
    expect(container.querySelector('blockquote')?.textContent).toContain('Body paragraph')
  })

  it('marker alone', async () => {
    const container = await renderPreview('> [!important]')

    expect(container.querySelector('blockquote')?.classList.contains('callout-important')).toBe(true)
    expect(container.querySelector('.callout-marker-labeled')).not.toBeNull()
  })

  it('aliases and bang-less markers resolve (grammar spot-check; full coverage in callouts.test)', async () => {
    const danger = await renderPreview('> [danger]\n> x')
    expect(danger.querySelector('blockquote')?.classList.contains('callout-caution')).toBe(true)

    const hint = await renderPreview('> [Hint] titled')
    expect(hint.querySelector('blockquote')?.classList.contains('callout-tip')).toBe(true)
  })

  it('unknown keyword renders a plain blockquote', async () => {
    const container = await renderPreview('> [!FOO]\n> Body')
    const blockquote = container.querySelector('blockquote')
    expect(blockquote).not.toBeNull()
    expect(blockquote?.classList.contains('callout')).toBe(false)
    expect(container.querySelector('.callout-marker')).toBeNull()
  })

  it('a blockquote with no marker is unaffected', async () => {
    const container = await renderPreview('> Just a quote')
    expect(container.querySelector('blockquote')?.classList.contains('callout')).toBe(false)
  })

  it('a marker not at the start of the first paragraph is not a callout', async () => {
    const container = await renderPreview('> Text before [!note]')
    expect(container.querySelector('blockquote')?.classList.contains('callout')).toBe(false)
  })

  it('the labeled marker carries its display label from the shared constant', async () => {
    const container = await renderPreview('> [!important]')
    // CSS renders the label via content: attr(data-callout-label), so the
    // shared CALLOUT_LABELS constant is the real source of the visible text.
    expect(container.querySelector('.callout-marker-labeled')?.getAttribute('data-callout-label')).toBe('Important')
  })
})

describe('cross-pipeline parity — contiguous explicitly-quoted lines', () => {
  // Narrow scope by design: this pins agreement between the editor's
  // line-model and the rendered view for CONTIGUOUS `>`-prefixed lines only.
  // It is not evidence of general structural parity (indented quotes, tilde
  // fences, and lazy continuation remain editor line-model limitations — see
  // the editor-improvements plan).
  const views: EditorView[] = []
  afterEach(() => {
    views.forEach((v) => v.destroy())
    views.length = 0
  })

  it('a mid-quote marker yields ONE note callout in both the editor and the reading view', async () => {
    const doc = '> [!note]\n> [!caution]\n> body'

    // Editor (CodeMirror line model)
    const parent = document.createElement('div')
    document.body.appendChild(parent)
    const view = new EditorView({
      state: EditorState.create({ doc, extensions: [markdownStyleExtension] }),
      parent,
    })
    views.push(view)
    const editorLines = Array.from(view.dom.querySelectorAll('.cm-line')).map((el) => el.className)
    expect(editorLines.every((c) => c.includes('cm-md-callout-note'))).toBe(true)
    expect(view.dom.querySelector('[class*="cm-md-callout-caution"]')).toBeNull()

    // Reading view (Milkdown)
    const rendered = await renderPreview(doc)
    const blockquotes = rendered.querySelectorAll('blockquote')
    expect(blockquotes).toHaveLength(1)
    expect(blockquotes[0].classList.contains('callout-note')).toBe(true)
    expect(rendered.querySelector('.callout-caution')).toBeNull()
    // The second marker is literal body text in both pipelines.
    expect(blockquotes[0].textContent).toContain('[!caution]')
  })
})
