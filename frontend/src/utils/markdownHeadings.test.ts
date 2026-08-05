import { describe, it, expect } from 'vitest'
import { parseMarkdownHeadings } from './markdownHeadings'

describe('parseMarkdownHeadings', () => {
  // ---------------------------------------------------------------------------
  // Core behavior
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__parses_h1_through_h6', () => {
    const text = [
      '# Heading 1',
      '## Heading 2',
      '### Heading 3',
      '#### Heading 4',
      '##### Heading 5',
      '###### Heading 6',
    ].join('\n')

    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Heading 1', line: 1 },
      { level: 2, text: 'Heading 2', line: 2 },
      { level: 3, text: 'Heading 3', line: 3 },
      { level: 4, text: 'Heading 4', line: 4 },
      { level: 5, text: 'Heading 5', line: 5 },
      { level: 6, text: 'Heading 6', line: 6 },
    ])
  })

  it('test__parseMarkdownHeadings__returns_headings_in_document_order', () => {
    const text = '## Second\n\nSome text\n\n# First\n\n### Third'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'Second', line: 1 },
      { level: 1, text: 'First', line: 5 },
      { level: 3, text: 'Third', line: 7 },
    ])
  })

  it('test__parseMarkdownHeadings__empty_document_returns_empty_array', () => {
    expect(parseMarkdownHeadings('')).toEqual([])
  })

  it('test__parseMarkdownHeadings__no_headings_returns_empty_array', () => {
    const text = 'Just some text.\n\nAnother paragraph.\n\n- A list item'
    expect(parseMarkdownHeadings(text)).toEqual([])
  })

  // ---------------------------------------------------------------------------
  // Code block handling
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__skips_headings_in_backtick_code_blocks', () => {
    const text = '# Real heading\n```\n## Fake heading\n```\n# Another real'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Real heading', line: 1 },
      { level: 1, text: 'Another real', line: 5 },
    ])
  })

  it('test__parseMarkdownHeadings__skips_headings_in_tilde_code_blocks', () => {
    const text = '# Before\n~~~\n## Inside\n~~~\n# After'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Before', line: 1 },
      { level: 1, text: 'After', line: 5 },
    ])
  })

  it('test__parseMarkdownHeadings__handles_nested_backticks_in_longer_fence', () => {
    // A ``` inside a ````` fence does NOT close it
    const text = [
      '# Before',
      '`````',
      '## Inside',
      '```',
      '## Still inside',
      '`````',
      '# After',
    ].join('\n')
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Before', line: 1 },
      { level: 1, text: 'After', line: 7 },
    ])
  })

  it('test__parseMarkdownHeadings__tilde_fence_not_closed_by_backticks', () => {
    const text = '~~~\n## Inside\n```\n## Still inside\n~~~\n# After'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'After', line: 6 },
    ])
  })

  it('test__parseMarkdownHeadings__code_fence_with_language_tag', () => {
    const text = '```python\n## Comment\n```\n# Real'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Real', line: 4 },
    ])
  })

  it('test__parseMarkdownHeadings__indented_code_fence', () => {
    const text = '  ```\n## Inside\n  ```\n# After'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'After', line: 4 },
    ])
  })

  it('test__parseMarkdownHeadings__closing_fence_with_trailing_whitespace', () => {
    const text = '```\n## Inside\n```   \n# After'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'After', line: 4 },
    ])
  })

  it('test__parseMarkdownHeadings__closing_fence_with_text_after_does_not_close', () => {
    // Per CommonMark, closing fence can't have content after (except whitespace)
    const text = '```\n## Inside\n``` not a close\n## Still inside\n```\n# After'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'After', line: 6 },
    ])
  })

  // ---------------------------------------------------------------------------
  // Heading syntax edge cases
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__hash_without_space_is_not_heading', () => {
    const text = '#hashtag\n##also not\n# Real heading'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Real heading', line: 3 },
    ])
  })

  it('test__parseMarkdownHeadings__hash_with_space_but_empty_text', () => {
    const text = '# \n## '
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: '', line: 1 },
      { level: 2, text: '', line: 2 },
    ])
  })

  it('test__parseMarkdownHeadings__hash_alone_on_line', () => {
    // Per CommonMark, the opening # sequence may be followed by spaces/tabs OR
    // by end of line — so a bare `#` IS a valid empty heading. (A previous
    // hand-rolled parser asserted the opposite; the renderer emits an h1 for
    // it, so ordinal parity requires reporting it.)
    const text = '#\n# '
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: '', line: 1 },
      { level: 1, text: '', line: 2 },
    ])
  })

  it('test__parseMarkdownHeadings__trims_leading_and_trailing_whitespace_in_text', () => {
    const text = '##   lots of spaces   '
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'lots of spaces', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__seven_hashes_is_not_a_heading', () => {
    const text = '####### Not a heading\n###### Real H6'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 6, text: 'Real H6', line: 2 },
    ])
  })

  // ---------------------------------------------------------------------------
  // Inline formatting cleaning
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__strips_bold_formatting', () => {
    const text = '## **bold** heading'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'bold heading', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__strips_italic_formatting', () => {
    const text = '## *italic* and _also italic_'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'italic and also italic', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__strips_inline_code', () => {
    const text = '## `code` thing'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'code thing', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__strips_strikethrough', () => {
    const text = '## ~~deleted~~ text'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'deleted text', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__strips_highlight', () => {
    const text = '## ==highlighted== text'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'highlighted text', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__preserves_underscores_in_identifiers', () => {
    const text = '## a_b_c'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'a_b_c', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__intraword_asterisks_are_emphasis_like_the_renderer', () => {
    // CommonMark allows intraword emphasis with * (unlike _): 2*3*4 renders
    // as 2<em>3</em>4, so the parsed text must match the rendered textContent.
    const text = '## 2*3*4'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: '234', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__strips_standalone_italic_markers', () => {
    const text = '## _italic_ and *also italic*'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'italic and also italic', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__strips_mixed_formatting', () => {
    const text = '## **bold** and *italic* and `code`'
    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 2, text: 'bold and italic and code', line: 1 },
    ])
  })

  // ---------------------------------------------------------------------------
  // Mixed content
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__extracts_only_headings_from_mixed_content', () => {
    const text = [
      '# Introduction',
      '',
      'Some paragraph text here.',
      '',
      '- List item 1',
      '- List item 2',
      '',
      '## Details',
      '',
      '> A blockquote',
      '',
      '```',
      '### Not a heading',
      '```',
      '',
      '### Conclusion',
      '',
      'Final paragraph.',
    ].join('\n')

    const result = parseMarkdownHeadings(text)
    expect(result).toEqual([
      { level: 1, text: 'Introduction', line: 1 },
      { level: 2, text: 'Details', line: 8 },
      { level: 3, text: 'Conclusion', line: 16 },
    ])
  })

  // ---------------------------------------------------------------------------
  // Setext headings (Text / === or ---) — rendered as h1/h2 by remark, so the
  // parser must report them for reading-mode ordinal parity.
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__setext_h1_and_h2_anchor_to_the_text_line', () => {
    const text = 'Title\n===\n\nSection\n---'
    expect(parseMarkdownHeadings(text)).toEqual([
      { level: 1, text: 'Title', line: 1 },
      { level: 2, text: 'Section', line: 4 },
    ])
  })

  it('test__parseMarkdownHeadings__single_char_setext_underline_counts', () => {
    expect(parseMarkdownHeadings('Title\n=')).toEqual([{ level: 1, text: 'Title', line: 1 }])
    expect(parseMarkdownHeadings('Title\n-')).toEqual([{ level: 2, text: 'Title', line: 1 }])
  })

  it('test__parseMarkdownHeadings__setext_underline_indented_up_to_three_spaces', () => {
    expect(parseMarkdownHeadings('Title\n   ===')).toEqual([{ level: 1, text: 'Title', line: 1 }])
  })

  it('test__parseMarkdownHeadings__setext_text_is_cleaned_of_inline_formatting', () => {
    expect(parseMarkdownHeadings('**Bold** title\n===')).toEqual([
      { level: 1, text: 'Bold title', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__dashes_after_blank_line_are_not_a_heading', () => {
    // A `---` with no paragraph above is a thematic break, not an underline.
    expect(parseMarkdownHeadings('Paragraph\n\n---')).toEqual([])
  })

  it('test__parseMarkdownHeadings__dashes_after_list_blockquote_or_atx_are_not_a_heading', () => {
    expect(parseMarkdownHeadings('- item\n---')).toEqual([])
    expect(parseMarkdownHeadings('> quote\n---')).toEqual([])
    // After an ATX heading, --- is a thematic break (the heading still parses).
    expect(parseMarkdownHeadings('# Heading\n---')).toEqual([
      { level: 1, text: 'Heading', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__dashes_after_a_thematic_break_are_not_a_heading', () => {
    expect(parseMarkdownHeadings('Text\n---\n---')).toEqual([
      { level: 2, text: 'Text', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__setext_inside_code_fence_is_ignored', () => {
    expect(parseMarkdownHeadings('```\nTitle\n===\n```')).toEqual([])
  })

  // ---------------------------------------------------------------------------
  // Indented ATX headings — CommonMark allows up to 3 leading spaces.
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__atx_indented_up_to_three_spaces', () => {
    const text = ' # One\n  ## Two\n   ### Three'
    expect(parseMarkdownHeadings(text)).toEqual([
      { level: 1, text: 'One', line: 1 },
      { level: 2, text: 'Two', line: 2 },
      { level: 3, text: 'Three', line: 3 },
    ])
  })

  it('test__parseMarkdownHeadings__atx_indented_four_spaces_is_code_not_heading', () => {
    expect(parseMarkdownHeadings('    # Not a heading')).toEqual([])
  })

  // ---------------------------------------------------------------------------
  // Link/image normalization — the rendered DOM shows only the text, and the
  // ToC panel should too.
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__reduces_links_to_their_text', () => {
    expect(parseMarkdownHeadings('# See [the docs](https://example.com) here')).toEqual([
      { level: 1, text: 'See the docs here', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__images_contribute_nothing_like_dom_textContent', () => {
    // An <img> contributes nothing to textContent, and reading-mode
    // verification compares parsed text against textContent — so alt text is
    // deliberately excluded (this is why the parser doesn't use
    // mdast-util-to-string, which would include it).
    expect(parseMarkdownHeadings('# Logo ![alt text](img.png) end')).toEqual([
      { level: 1, text: 'Logo end', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__link_with_bold_text_fully_cleaned', () => {
    expect(parseMarkdownHeadings('# [**Bold link**](url)')).toEqual([
      { level: 1, text: 'Bold link', line: 1 },
    ])
  })

  // ---------------------------------------------------------------------------
  // CommonMark forms the renderer emits that a hand-rolled parser missed —
  // each of these shifts reading-mode ordinals if skipped or mis-texted.
  // ---------------------------------------------------------------------------

  it('test__parseMarkdownHeadings__closing_sequence_is_stripped', () => {
    // ATX closing sequences: `# Title #` renders as "Title".
    expect(parseMarkdownHeadings('# Title #\n## Sub ##')).toEqual([
      { level: 1, text: 'Title', line: 1 },
      { level: 2, text: 'Sub', line: 2 },
    ])
  })

  it('test__parseMarkdownHeadings__tab_after_hashes_is_a_heading', () => {
    expect(parseMarkdownHeadings('#\tTitle')).toEqual([
      { level: 1, text: 'Title', line: 1 },
    ])
  })

  it('test__parseMarkdownHeadings__multiline_setext_reports_full_text_anchored_to_first_line', () => {
    // A multi-line paragraph promoted by an underline is ALL heading text, and
    // the heading anchors to the paragraph's FIRST line (navigation should
    // land at the heading's start). Both differ from the previous hand-rolled
    // parser, which reported only the last line — deliberate behavior change.
    expect(parseMarkdownHeadings('First line\nsecond line\n===')).toEqual([
      { level: 1, text: 'First line second line', line: 1 },
    ])
  })
})
