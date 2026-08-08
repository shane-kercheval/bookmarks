/**
 * Tests for ContentEditor's reader mode (public share view): the character
 * counter is hidden, and the underlying editor is driven read-only but
 * selectable (disabled:false + readOnly:true) with the reader-mode flag set.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ContentEditor } from './ContentEditor'

interface RecordedProps {
  readerMode?: boolean
  defaultReadingMode?: boolean
  disabled?: boolean
  readOnly?: boolean
  itemId?: string
  itemIdWasJustCreated?: boolean
}
let lastProps: RecordedProps = {}

vi.mock('./CodeMirrorEditor', () => ({
  CodeMirrorEditor: (props: RecordedProps & { value: string }) => {
    lastProps = props
    return <textarea data-testid="cm" value={props.value} onChange={() => {}} />
  },
}))

describe('ContentEditor — reader mode', () => {
  it('hides the character counter and drives the editor read-only + selectable', () => {
    render(
      <ContentEditor value="Hello" onChange={() => {}} maxLength={1000} readerMode defaultReadingMode itemId="n1" />
    )
    expect(screen.queryByText(/\/\s*1,000/)).toBeNull() // no "5 / 1,000" counter
    expect(lastProps.readerMode).toBe(true)
    expect(lastProps.defaultReadingMode).toBe(true)
    expect(lastProps.disabled).toBe(false)
    expect(lastProps.readOnly).toBe(true)
    // itemId + create signal thread through for per-item reading-mode persistence.
    expect(lastProps.itemId).toBe('n1')
    expect(lastProps.itemIdWasJustCreated).toBe(false)
  })

  it('shows the counter and respects disabled when not in reader mode', () => {
    render(<ContentEditor value="Hello" onChange={() => {}} maxLength={1000} disabled />)
    expect(screen.getByText(/\/\s*1,000/)).toBeInTheDocument()
    expect(lastProps.readerMode).toBe(false)
    expect(lastProps.disabled).toBe(true)
  })
})
