/**
 * Tests for markdown style extension helper functions.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { _testExports, markdownStyleExtension } from './markdownStyleExtension'

const {
  findImages,
  findLinks,
  findInlineCode,
  findStrikethrough,
  findHighlight,
  findBold,
  findItalic,
  findBlockquoteSyntax,
  findJinjaExpressions,
  parseLine,
  handleEditorMousedown,
  handleEditorClick,
  handleEditorMousemove,
  handleEditorMouseleave,
  handleEditorKeyup,
} = _testExports

/**
 * Build a minimal EditorView for handler tests. jsdom doesn't compute layout,
 * so we stub `posAtCoords` to return a fixed document position — handlers call
 * it with client coords and only care about the returned doc position.
 */
function buildView(doc: string, posAtCoordsReturn: number | null): EditorView {
  const parent = document.createElement('div')
  const view = new EditorView({
    state: EditorState.create({ doc, extensions: [markdownStyleExtension] }),
    parent,
  })
  vi.spyOn(view, 'posAtCoords').mockReturnValue(posAtCoordsReturn)
  return view
}

function makeMouseEvent(init: Partial<MouseEventInit> = {}, target?: HTMLElement): MouseEvent {
  const event = new MouseEvent('mousedown', { button: 0, ...init })
  // Give the event a non-null target so handler code that reads target.classList works.
  Object.defineProperty(event, 'target', { value: target ?? document.createElement('div') })
  vi.spyOn(event, 'preventDefault')
  return event
}

describe('findImages', () => {
  it('should find a simple image', () => {
    const result = findImages('![alt text](https://example.com/image.png)')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(0)
    expect(result[0].to).toBe(42)
  })

  it('should find multiple images', () => {
    const result = findImages('![img1](url1) text ![img2](url2)')
    expect(result).toHaveLength(2)
  })

  it('should find image with empty alt text', () => {
    const result = findImages('![](https://example.com/image.png)')
    expect(result).toHaveLength(1)
    expect(result[0].altStart).toBe(result[0].altEnd) // Empty alt
  })

  it('should not match regular links', () => {
    const result = findImages('[not an image](https://example.com)')
    expect(result).toHaveLength(0)
  })

  it('should return empty array for text without images', () => {
    const result = findImages('Just some regular text')
    expect(result).toHaveLength(0)
  })

  it('should correctly identify component positions', () => {
    const text = '![alt](url)'
    const result = findImages(text)
    expect(result).toHaveLength(1)
    const img = result[0]
    expect(img.exclamation).toBe(0)     // !
    expect(img.openBracket).toBe(1)     // [
    expect(img.altStart).toBe(2)        // a
    expect(img.altEnd).toBe(5)          // after "alt"
    expect(img.closeBracket).toBe(5)    // ]
    expect(img.openParen).toBe(6)       // (
    expect(img.urlStart).toBe(7)        // u
    expect(img.urlEnd).toBe(10)         // after "url"
    expect(img.closeParen).toBe(10)     // )
  })

  it('should handle image at end of line with other content', () => {
    const text = 'Some text before ![image](url)'
    const result = findImages(text)
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(17) // "Some text before " is 17 chars
  })
})

describe('findLinks', () => {
  it('should find a simple link', () => {
    const result = findLinks('[link text](https://example.com)')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(0)
    expect(result[0].url).toBe('https://example.com')
  })

  it('should find multiple links', () => {
    const result = findLinks('[link1](url1) and [link2](url2)')
    expect(result).toHaveLength(2)
    expect(result[0].url).toBe('url1')
    expect(result[1].url).toBe('url2')
  })

  it('should return empty array for text without links', () => {
    const result = findLinks('Just some regular text')
    expect(result).toHaveLength(0)
  })

  it('should correctly identify component positions', () => {
    const text = '[text](url)'
    const result = findLinks(text)
    expect(result).toHaveLength(1)
    const link = result[0]
    expect(link.openBracket).toBe(0)    // [
    expect(link.textStart).toBe(1)      // t
    expect(link.textEnd).toBe(5)        // after "text"
    expect(link.closeBracket).toBe(5)   // ]
    expect(link.openParen).toBe(6)      // (
    expect(link.urlStart).toBe(7)       // u
    expect(link.urlEnd).toBe(10)        // after "url"
    expect(link.closeParen).toBe(10)    // )
  })

  it('should handle link with spaces in text', () => {
    const result = findLinks('[link with spaces](url)')
    expect(result).toHaveLength(1)
    expect(result[0].textEnd - result[0].textStart).toBe(16) // "link with spaces"
  })

  it('should also match image syntax (![...](...)) - filtered separately', () => {
    // Note: findLinks matches both links and the link portion of images
    // The buildDecorations function filters these out
    const result = findLinks('![image](url)')
    expect(result).toHaveLength(1)
  })
})

describe('findInlineCode', () => {
  it('should find single inline code', () => {
    const result = findInlineCode('Use `code` here')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(4)
    expect(result[0].to).toBe(10)
  })

  it('should find multiple inline code spans', () => {
    const result = findInlineCode('`first` and `second`')
    expect(result).toHaveLength(2)
  })

  it('should not match at start of triple backticks', () => {
    // Note: This function is used in combination with code block detection
    // which handles ``` lines separately. The function avoids matching
    // the first two backticks but may match content after.
    const result = findInlineCode('```')
    expect(result).toHaveLength(0)
  })

  it('should return empty array for text without inline code', () => {
    const result = findInlineCode('Just regular text')
    expect(result).toHaveLength(0)
  })

  it('should handle unclosed backtick', () => {
    const result = findInlineCode('`unclosed')
    expect(result).toHaveLength(0)
  })

  it('should not match two consecutive backticks as code', () => {
    const result = findInlineCode('``')
    // Two consecutive backticks are skipped (could be part of ```)
    expect(result).toHaveLength(0)
  })

  it('should match code with content between backticks', () => {
    const result = findInlineCode('`x`')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(0)
    expect(result[0].to).toBe(3)
  })

  it('should correctly identify marker and content positions', () => {
    const result = findInlineCode('`code`')
    expect(result).toHaveLength(1)
    const code = result[0]
    expect(code.markerStart).toBe(0)    // Opening `
    expect(code.contentStart).toBe(1)   // c
    expect(code.contentEnd).toBe(5)     // after "code"
    expect(code.markerEnd).toBe(6)      // after closing `
  })
})

describe('findStrikethrough', () => {
  it('should find strikethrough text', () => {
    const result = findStrikethrough('This is ~~deleted~~ text')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(8)
    expect(result[0].to).toBe(19)
  })

  it('should find multiple strikethroughs', () => {
    const result = findStrikethrough('~~first~~ and ~~second~~')
    expect(result).toHaveLength(2)
  })

  it('should return empty array for text without strikethrough', () => {
    const result = findStrikethrough('Regular text')
    expect(result).toHaveLength(0)
  })

  it('should not match single tildes', () => {
    const result = findStrikethrough('~not strikethrough~')
    expect(result).toHaveLength(0)
  })

  it('should correctly identify marker and content positions', () => {
    const result = findStrikethrough('~~deleted~~')
    expect(result).toHaveLength(1)
    const strike = result[0]
    expect(strike.markerStart).toBe(0)      // Opening ~~
    expect(strike.markerStartEnd).toBe(2)   // After opening ~~
    expect(strike.contentStart).toBe(2)     // d
    expect(strike.contentEnd).toBe(9)       // After "deleted"
    expect(strike.markerEndStart).toBe(9)   // Before closing ~~
    expect(strike.markerEnd).toBe(11)       // After closing ~~
  })
})

describe('findHighlight', () => {
  it('should find highlight text', () => {
    const result = findHighlight('This is ==important== text')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(8)
    expect(result[0].to).toBe(21)
  })

  it('should find multiple highlights', () => {
    const result = findHighlight('==first== and ==second==')
    expect(result).toHaveLength(2)
  })

  it('should return empty array for text without highlight', () => {
    const result = findHighlight('Regular text')
    expect(result).toHaveLength(0)
  })

  it('should not match single equals', () => {
    const result = findHighlight('=not highlight=')
    expect(result).toHaveLength(0)
  })

  it('should correctly identify marker and content positions', () => {
    const result = findHighlight('==highlight==')
    expect(result).toHaveLength(1)
    const hl = result[0]
    expect(hl.markerStart).toBe(0)      // Opening ==
    expect(hl.markerStartEnd).toBe(2)   // After opening ==
    expect(hl.contentStart).toBe(2)     // h
    expect(hl.contentEnd).toBe(11)      // After "highlight"
    expect(hl.markerEndStart).toBe(11)  // Before closing ==
    expect(hl.markerEnd).toBe(13)       // After closing ==
  })
})

describe('findBold', () => {
  it('should find bold text', () => {
    const result = findBold('This is **bold** text')
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(8)
    expect(result[0].to).toBe(16)
  })

  it('should find multiple bold spans', () => {
    const result = findBold('**first** and **second**')
    expect(result).toHaveLength(2)
  })

  it('should return empty array for text without bold', () => {
    const result = findBold('Regular text')
    expect(result).toHaveLength(0)
  })

  it('should not match single asterisks (italic)', () => {
    const result = findBold('*not bold*')
    expect(result).toHaveLength(0)
  })

  it('should correctly identify marker and content positions', () => {
    const result = findBold('**bold**')
    expect(result).toHaveLength(1)
    const bold = result[0]
    expect(bold.markerStart).toBe(0)      // Opening **
    expect(bold.markerStartEnd).toBe(2)   // After opening **
    expect(bold.contentStart).toBe(2)     // b
    expect(bold.contentEnd).toBe(6)       // After "bold"
    expect(bold.markerEndStart).toBe(6)   // Before closing **
    expect(bold.markerEnd).toBe(8)        // After closing **
  })
})

describe('findItalic', () => {
  it('should find italic text', () => {
    const boldMatches = findBold('This is *italic* text')
    const result = findItalic('This is *italic* text', boldMatches)
    expect(result).toHaveLength(1)
    expect(result[0].from).toBe(8)
    expect(result[0].to).toBe(16)
  })

  it('should find multiple italic spans', () => {
    const text = '*first* and *second*'
    const boldMatches = findBold(text)
    const result = findItalic(text, boldMatches)
    expect(result).toHaveLength(2)
  })

  it('should return empty array for text without italic', () => {
    const boldMatches = findBold('Regular text')
    const result = findItalic('Regular text', boldMatches)
    expect(result).toHaveLength(0)
  })

  it('should not match double asterisks (bold)', () => {
    const text = '**not italic**'
    const boldMatches = findBold(text)
    const result = findItalic(text, boldMatches)
    expect(result).toHaveLength(0)
  })

  it('should correctly identify marker and content positions', () => {
    const text = '*italic*'
    const boldMatches = findBold(text)
    const result = findItalic(text, boldMatches)
    expect(result).toHaveLength(1)
    const italic = result[0]
    expect(italic.markerStart).toBe(0)      // Opening *
    expect(italic.markerStartEnd).toBe(1)   // After opening *
    expect(italic.contentStart).toBe(1)     // i
    expect(italic.contentEnd).toBe(7)       // After "italic"
    expect(italic.markerEndStart).toBe(7)   // Before closing *
    expect(italic.markerEnd).toBe(8)        // After closing *
  })

  it('should exclude italic spans that overlap with bold', () => {
    const text = '**bold** and *italic*'
    const boldMatches = findBold(text)
    const result = findItalic(text, boldMatches)
    // Should only find the italic, not the * inside **
    expect(result).toHaveLength(1)
    expect(result[0].contentStart).toBe(14) // "italic" starts at position 14
  })
})

describe('findBlockquoteSyntax', () => {
  it('should find blockquote with space', () => {
    const result = findBlockquoteSyntax('> Quote text')
    expect(result).not.toBeNull()
    expect(result?.from).toBe(0)
    expect(result?.to).toBe(2) // "> "
  })

  it('should find blockquote without space', () => {
    const result = findBlockquoteSyntax('>Quote text')
    expect(result).not.toBeNull()
    expect(result?.from).toBe(0)
    expect(result?.to).toBe(1) // ">"
  })

  it('should return null for non-blockquote', () => {
    const result = findBlockquoteSyntax('Regular text')
    expect(result).toBeNull()
  })

  it('should return null for > not at start', () => {
    const result = findBlockquoteSyntax('Text > with arrow')
    expect(result).toBeNull()
  })
})

describe('parseLine', () => {
  describe('headers', () => {
    it('should detect h1', () => {
      const result = parseLine('# Header 1', false)
      expect(result?.type).toBe('h1')
    })

    it('should detect h2', () => {
      const result = parseLine('## Header 2', false)
      expect(result?.type).toBe('h2')
    })

    it('should detect h3', () => {
      const result = parseLine('### Header 3', false)
      expect(result?.type).toBe('h3')
    })

    it('should detect h4', () => {
      const result = parseLine('#### Header 4', false)
      expect(result?.type).toBe('h4')
    })

    it('should detect h5', () => {
      const result = parseLine('##### Header 5', false)
      expect(result?.type).toBe('h5')
    })

    it('should detect h6', () => {
      const result = parseLine('###### Header 6', false)
      expect(result?.type).toBe('h6')
    })

    it('should require space after #', () => {
      const result = parseLine('#NoSpace', false)
      expect(result).toBeNull()
    })
  })

  describe('lists', () => {
    it('should detect bullet list with -', () => {
      const result = parseLine('- Item', false)
      expect(result?.type).toBe('bullet')
    })

    it('should detect bullet list with *', () => {
      const result = parseLine('* Item', false)
      expect(result?.type).toBe('bullet')
    })

    it('should detect bullet list with +', () => {
      const result = parseLine('+ Item', false)
      expect(result?.type).toBe('bullet')
    })

    it('should detect numbered list', () => {
      const result = parseLine('1. Item', false)
      expect(result?.type).toBe('numbered')
    })

    it('should detect numbered list with larger numbers', () => {
      const result = parseLine('123. Item', false)
      expect(result?.type).toBe('numbered')
    })

    // prefixLen powers the per-line hanging-indent CSS variable so wrapped
    // list lines align with the content after the marker (KAN-111).
    describe('prefixLen (hanging indent width)', () => {
      it('returns 2 for "- Item"', () => {
        expect(parseLine('- Item', false)?.prefixLen).toBe(2)
      })

      it('returns 3 for "1. Item"', () => {
        expect(parseLine('1. Item', false)?.prefixLen).toBe(3)
      })

      it('returns 5 for "123. Item"', () => {
        expect(parseLine('123. Item', false)?.prefixLen).toBe(5)
      })

      it('includes leading indent for nested bullet', () => {
        expect(parseLine('  - Nested', false)?.prefixLen).toBe(4)
      })

      it('includes leading indent for deeply nested bullet', () => {
        expect(parseLine('      - Deep', false)?.prefixLen).toBe(8)
      })

      it('returns 6 for "- [ ] Item"', () => {
        expect(parseLine('- [ ] Item', false)?.prefixLen).toBe(6)
      })

      it('includes leading indent for nested checklist', () => {
        expect(parseLine('  - [x] Nested', false)?.prefixLen).toBe(8)
      })
    })
  })

  describe('checklist', () => {
    it('should detect unchecked checklist item', () => {
      const result = parseLine('- [ ] Item', false)
      expect(result?.type).toBe('checklist')
      expect(result?.checked).toBe(false)
    })

    it('should detect checked checklist item', () => {
      const result = parseLine('- [x] Item', false)
      expect(result?.type).toBe('checklist')
      expect(result?.checked).toBe(true)
    })

    it('should detect checked checklist item with uppercase X', () => {
      const result = parseLine('- [X] Item', false)
      expect(result?.type).toBe('checklist')
      expect(result?.checked).toBe(true)
    })

    it('should provide bracket position', () => {
      const result = parseLine('- [ ] Item', false)
      expect(result?.bracketPos).toBe(2)  // Position of [ for editing
    })

    it('should handle indented checklist items', () => {
      const result = parseLine('  - [ ] Nested item', false)
      expect(result?.type).toBe('checklist')
      expect(result?.bracketPos).toBe(4)  // Position of [ for editing
    })

    // bracketPos is now computed from the actual match position of "[" so it
    // stays correct for multi-space variants. The click-to-toggle handler
    // dispatches a 3-character replacement at bracketPos; if this were off by
    // one, the toggle would corrupt the line.
    it('returns correct bracketPos for multi-space between marker and [', () => {
      expect(parseLine('-  [ ] Item', false)?.bracketPos).toBe(3)
    })

    it('returns correct bracketPos for indent + multi-space', () => {
      expect(parseLine('  -  [x] Item', false)?.bracketPos).toBe(5)
    })
  })

  describe('blockquotes', () => {
    it('should detect blockquote', () => {
      const result = parseLine('> Quote', false)
      expect(result?.type).toBe('blockquote')
    })

    it('should detect blockquote without space', () => {
      const result = parseLine('>Quote', false)
      expect(result?.type).toBe('blockquote')
    })
  })

  describe('code blocks', () => {
    it('should detect code block start', () => {
      const result = parseLine('```javascript', false)
      expect(result?.type).toBe('code-start')
    })

    it('should detect code block end', () => {
      const result = parseLine('```', true)
      expect(result?.type).toBe('code-end')
    })

    it('should detect code content', () => {
      const result = parseLine('const x = 1;', true)
      expect(result?.type).toBe('code-content')
    })
  })

  describe('horizontal rules', () => {
    it('should detect hr with dashes', () => {
      const result = parseLine('---', false)
      expect(result?.type).toBe('hr')
    })

    it('should detect hr with asterisks', () => {
      const result = parseLine('***', false)
      expect(result?.type).toBe('hr')
    })

    it('should detect hr with underscores', () => {
      const result = parseLine('___', false)
      expect(result?.type).toBe('hr')
    })

    it('should detect hr with more than 3 characters', () => {
      const result = parseLine('-----', false)
      expect(result?.type).toBe('hr')
    })
  })

  describe('regular text', () => {
    it('should return null for regular text', () => {
      const result = parseLine('Just some text', false)
      expect(result).toBeNull()
    })

    it('should return null for empty line', () => {
      const result = parseLine('', false)
      expect(result).toBeNull()
    })
  })
})

describe('findJinjaExpressions', () => {
  describe('variables', () => {
    it('should find a simple variable', () => {
      const result = findJinjaExpressions('Hello {{ name }}!')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
      expect(result[0].from).toBe(6)
      expect(result[0].to).toBe(16)
    })

    it('should find variable without spaces', () => {
      const result = findJinjaExpressions('{{name}}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
      expect(result[0].from).toBe(0)
      expect(result[0].to).toBe(8)
    })

    it('should find multiple variables', () => {
      const result = findJinjaExpressions('{{ first }} and {{ second }}')
      expect(result).toHaveLength(2)
      expect(result[0].type).toBe('variable')
      expect(result[1].type).toBe('variable')
    })

    it('should find variable with filter', () => {
      const result = findJinjaExpressions('{{ name|upper }}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
    })

    it('should correctly identify delimiter and content positions', () => {
      const result = findJinjaExpressions('{{ name }}')
      expect(result).toHaveLength(1)
      const v = result[0]
      expect(v.openDelimFrom).toBe(0)    // {{
      expect(v.openDelimTo).toBe(2)      // after {{
      expect(v.contentStart).toBe(2)     // space before name
      expect(v.contentEnd).toBe(8)       // after "name "
      expect(v.closeDelimFrom).toBe(8)   // }}
      expect(v.closeDelimTo).toBe(10)    // after }}
    })
  })

  describe('tags', () => {
    it('should find a simple block tag', () => {
      const result = findJinjaExpressions('{% if active %}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
      expect(result[0].from).toBe(0)
      expect(result[0].to).toBe(15)
    })

    it('should find tag with leading trim', () => {
      const result = findJinjaExpressions('{%- if active %}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
      expect(result[0].openDelimTo).toBe(3) // {%-
    })

    it('should find tag with trailing trim', () => {
      const result = findJinjaExpressions('{% if active -%}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
      expect(result[0].closeDelimFrom).toBe(13) // -%}
    })

    it('should find tag with both trims', () => {
      const result = findJinjaExpressions('{%- if active -%}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
      expect(result[0].openDelimTo).toBe(3)     // {%-
      expect(result[0].closeDelimFrom).toBe(14)  // -%}
    })

    it('should find endif tag', () => {
      const result = findJinjaExpressions('{% endif %}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
    })

    it('should find for loop tag', () => {
      const result = findJinjaExpressions('{% for item in items %}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
    })
  })

  describe('comments', () => {
    it('should find a comment', () => {
      const result = findJinjaExpressions('{# This is a comment #}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('comment')
      expect(result[0].from).toBe(0)
      expect(result[0].to).toBe(23)
    })

    it('should correctly identify comment positions', () => {
      const result = findJinjaExpressions('{# note #}')
      expect(result).toHaveLength(1)
      const c = result[0]
      expect(c.openDelimFrom).toBe(0)
      expect(c.openDelimTo).toBe(2)
      expect(c.contentStart).toBe(2)
      expect(c.contentEnd).toBe(8)
      expect(c.closeDelimFrom).toBe(8)
      expect(c.closeDelimTo).toBe(10)
    })
  })

  describe('mixed syntax', () => {
    it('should find multiple types on one line', () => {
      const result = findJinjaExpressions('{% if x %}{{ y }}{# z #}')
      expect(result).toHaveLength(3)
      expect(result[0].type).toBe('tag')
      expect(result[1].type).toBe('variable')
      expect(result[2].type).toBe('comment')
    })
  })

  describe('whitespace-control trim syntax', () => {
    it('should find variable with leading trim {{-', () => {
      const result = findJinjaExpressions('{{- name }}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
      expect(result[0].from).toBe(0)
      expect(result[0].to).toBe(11)
    })

    it('should find variable with trailing trim -}}', () => {
      const result = findJinjaExpressions('{{ name -}}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
    })

    it('should find variable with both trims', () => {
      const result = findJinjaExpressions('{{- name -}}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
    })

    it('should find comment with trims', () => {
      const result = findJinjaExpressions('{#- hidden -#}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('comment')
    })
  })

  describe('compact tag spacing', () => {
    it('should find tag without spaces', () => {
      const result = findJinjaExpressions('{%if x%}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
    })

    it('should find tag with no trailing space', () => {
      const result = findJinjaExpressions('{% endif%}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
    })

    it('should find trim tag without spaces', () => {
      const result = findJinjaExpressions('{%-endif-%}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('tag')
    })
  })

  describe('edge cases', () => {
    it('should return empty array for text without Jinja', () => {
      const result = findJinjaExpressions('Just regular text')
      expect(result).toHaveLength(0)
    })

    it('should not match single braces', () => {
      const result = findJinjaExpressions('{ not jinja }')
      expect(result).toHaveLength(0)
    })

    it('should not match unclosed expression', () => {
      const result = findJinjaExpressions('{{ unclosed')
      expect(result).toHaveLength(0)
    })

    it('should match empty variable expression', () => {
      const result = findJinjaExpressions('{{}}')
      expect(result).toHaveLength(1)
      expect(result[0].type).toBe('variable')
    })
  })
})

describe('link dom event handlers', () => {
  let views: EditorView[] = []

  beforeEach(() => {
    views = []
  })

  afterEach(() => {
    views.forEach((v) => v.destroy())
    vi.restoreAllMocks()
  })

  function track(view: EditorView): EditorView {
    views.push(view)
    return view
  }

  describe('handleEditorMousedown — cmd/ctrl intercept', () => {
    it('returns true and prevents default when cmd+mousedown over a link', () => {
      const doc = 'see [example](https://example.com) here'
      // position 6 is inside "[example]"
      const view = track(buildView(doc, 6))
      const event = makeMouseEvent({ metaKey: true })

      const handled = handleEditorMousedown(event, view)

      expect(handled).toBe(true)
      expect(event.preventDefault).toHaveBeenCalled()
    })

    it('does not intercept cmd+mousedown outside a link', () => {
      const doc = 'plain text without any link'
      const view = track(buildView(doc, 3))
      const event = makeMouseEvent({ metaKey: true })

      const handled = handleEditorMousedown(event, view)

      expect(handled).toBe(false)
      expect(event.preventDefault).not.toHaveBeenCalled()
    })

    it('does not intercept plain mousedown over a link', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      const event = makeMouseEvent({})

      const handled = handleEditorMousedown(event, view)

      expect(handled).toBe(false)
      expect(event.preventDefault).not.toHaveBeenCalled()
    })

    it('also intercepts ctrl+mousedown over a link', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      const event = makeMouseEvent({ ctrlKey: true })

      expect(handleEditorMousedown(event, view)).toBe(true)
    })

    it('treats url portion of [title](url) as part of the link', () => {
      const doc = 'see [example](https://example.com) here'
      // position 20 is inside the URL
      const view = track(buildView(doc, 20))
      const event = makeMouseEvent({ metaKey: true })

      expect(handleEditorMousedown(event, view)).toBe(true)
    })
  })

  describe('handleEditorClick — open link', () => {
    it('opens link via window.open when cmd+click over a link', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
      const event = makeMouseEvent({ metaKey: true })

      const handled = handleEditorClick(event, view)

      expect(handled).toBe(true)
      expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer')
      expect(event.preventDefault).toHaveBeenCalled()
    })

    it('prepends https:// when URL lacks a scheme', () => {
      const doc = '[bare](example.com)'
      const view = track(buildView(doc, 3))
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
      const event = makeMouseEvent({ metaKey: true })

      handleEditorClick(event, view)

      expect(openSpy).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer')
    })

    it('does nothing on plain click', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
      const event = makeMouseEvent({})

      const handled = handleEditorClick(event, view)

      expect(handled).toBe(false)
      expect(openSpy).not.toHaveBeenCalled()
    })

    it('does not open when cmd+click outside a link', () => {
      const doc = 'plain text without any link'
      const view = track(buildView(doc, 3))
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
      const event = makeMouseEvent({ metaKey: true })

      expect(handleEditorClick(event, view)).toBe(false)
      expect(openSpy).not.toHaveBeenCalled()
    })
  })

  describe('handleEditorMousemove — pointer cursor', () => {
    it('adds link-hover class when cmd held over a link', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      const event = makeMouseEvent({ metaKey: true })

      handleEditorMousemove(event, view)

      expect(view.dom.classList.contains('cm-md-link-hover')).toBe(true)
    })

    it('removes link-hover class when cmd no longer held', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      view.dom.classList.add('cm-md-link-hover')
      const event = makeMouseEvent({})

      handleEditorMousemove(event, view)

      expect(view.dom.classList.contains('cm-md-link-hover')).toBe(false)
    })

    it('does not add link-hover class when cmd held but not over a link', () => {
      const doc = 'plain text with no links here'
      const view = track(buildView(doc, 5))
      const event = makeMouseEvent({ metaKey: true })

      handleEditorMousemove(event, view)

      expect(view.dom.classList.contains('cm-md-link-hover')).toBe(false)
    })

    it('does not touch inline cursor style on contentDOM', () => {
      // Guards the ownership invariant: this handler should not mutate
      // inline cursor styles it doesn't own.
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      view.contentDOM.style.cursor = 'text'
      const event = makeMouseEvent({})

      handleEditorMousemove(event, view)

      expect(view.contentDOM.style.cursor).toBe('text')
    })
  })

  describe('handleEditorMouseleave', () => {
    it('removes link-hover class on mouseleave', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      view.dom.classList.add('cm-md-link-hover')

      handleEditorMouseleave(new MouseEvent('mouseleave'), view)

      expect(view.dom.classList.contains('cm-md-link-hover')).toBe(false)
    })

    it('does not touch inline cursor style on contentDOM', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      view.contentDOM.style.cursor = 'text'

      handleEditorMouseleave(new MouseEvent('mouseleave'), view)

      expect(view.contentDOM.style.cursor).toBe('text')
    })
  })

  describe('handleEditorKeyup', () => {
    it('removes link-hover class when cmd is released', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      view.dom.classList.add('cm-md-link-hover')
      const event = new KeyboardEvent('keyup', { key: 'Meta' })

      handleEditorKeyup(event, view)

      expect(view.dom.classList.contains('cm-md-link-hover')).toBe(false)
    })

    it('does not remove link-hover class while cmd still held', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      view.dom.classList.add('cm-md-link-hover')
      const event = new KeyboardEvent('keyup', { key: 'a', metaKey: true })

      handleEditorKeyup(event, view)

      expect(view.dom.classList.contains('cm-md-link-hover')).toBe(true)
    })
  })

  describe('cmd+click end-to-end sequence', () => {
    // Core contract of the fix: mousedown intercepts to prevent multi-cursor,
    // and the subsequent click still opens the link with a single selection.
    it('opens link and preserves single selection across mousedown+click', () => {
      const doc = 'see [example](https://example.com) here'
      const view = track(buildView(doc, 6))
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

      const initialRangeCount = view.state.selection.ranges.length

      const mousedown = makeMouseEvent({ metaKey: true })
      const mousedownHandled = handleEditorMousedown(mousedown, view)

      const click = makeMouseEvent({ metaKey: true })
      const clickHandled = handleEditorClick(click, view)

      expect(mousedownHandled).toBe(true)
      expect(clickHandled).toBe(true)
      expect(openSpy).toHaveBeenCalledWith(
        'https://example.com',
        '_blank',
        'noopener,noreferrer',
      )
      // Selection untouched — no secondary cursor added.
      expect(view.state.selection.ranges.length).toBe(initialRangeCount)
    })
  })

  describe('checklist toggle on multi-space lines', () => {
    // Locks in the bracketPos fix: parseLine now derives bracketPos from the
    // actual match position of "[" so the click-to-toggle handler correctly
    // replaces the 3-char checkbox even when there are multiple spaces
    // between the marker and "[". Before the fix, bracketPos was hardcoded
    // off-by-N and the toggle would corrupt the line.
    it('toggles "[ ]" → "[x]" on a line with multi-space marker spacing', () => {
      const doc = '-  [ ] Item'
      // Any pos inside the line works; the handler re-derives bracketPos
      // from parseLine on the line's text. Position 3 is "[".
      const view = track(buildView(doc, 3))

      const target = document.createElement('span')
      target.className = 'cm-md-checklist-checkbox cm-md-checklist-checkbox-unchecked'
      const event = makeMouseEvent({}, target)

      const handled = handleEditorMousedown(event, view)

      expect(handled).toBe(true)
      expect(view.state.doc.toString()).toBe('-  [x] Item')
    })

    it('toggles "[x]" → "[ ]" on an indented multi-space line', () => {
      const doc = '  -  [x] Item'
      const view = track(buildView(doc, 5))

      const target = document.createElement('span')
      target.className = 'cm-md-checklist-checkbox cm-md-checklist-checkbox-checked'
      const event = makeMouseEvent({}, target)

      handleEditorMousedown(event, view)

      expect(view.state.doc.toString()).toBe('  -  [ ] Item')
    })
  })
})

describe('callouts (CodeMirror editor)', () => {
  // DOM-level assertions against a real EditorView so the full path
  // (parseLine → buildDecorations threading → line classes) is exercised.
  const views: EditorView[] = []
  afterEach(() => {
    views.forEach((v) => v.destroy())
    views.length = 0
  })
  function mount(doc: string): HTMLElement {
    const parent = document.createElement('div')
    document.body.appendChild(parent)
    const view = new EditorView({
      state: EditorState.create({ doc, extensions: [markdownStyleExtension] }),
      parent,
    })
    views.push(view)
    return view.dom
  }
  function lineClasses(dom: HTMLElement): string[] {
    return Array.from(dom.querySelectorAll('.cm-line')).map((el) => el.className)
  }

  it('marker line gets the variant class and the marker span is dimmed', () => {
    const dom = mount('> [!WARNING] heads up')
    expect(dom.querySelector('.cm-md-callout-warning')).not.toBeNull()
    const marker = dom.querySelector('.cm-md-callout-marker')
    expect(marker?.textContent).toBe('[!WARNING]')
  })

  it('continuation lines inherit the variant; the blockquote end resets it', () => {
    const dom = mount('> [!note]\n> body line\n\nplain text')
    const classes = lineClasses(dom)
    expect(classes[0]).toContain('cm-md-callout-note')
    expect(classes[1]).toContain('cm-md-callout-note')
    expect(classes[2] ?? '').not.toContain('cm-md-callout')
    expect(classes[3] ?? '').not.toContain('cm-md-callout')
  })

  it('a plain quote before a marker does not inherit; a marker mid-document starts fresh', () => {
    const dom = mount('> plain quote\n\n> [!tip]\n> tip body')
    const classes = lineClasses(dom)
    expect(classes[0]).not.toContain('cm-md-callout')
    expect(classes[2]).toContain('cm-md-callout-tip')
    expect(classes[3]).toContain('cm-md-callout-tip')
  })

  it('blank-line-separated callouts are both recognized (opener-gate overcorrection guard)', () => {
    // Two callouts separated by a blank unquoted line are two blockquotes —
    // both markers sit on quote-opening lines and both must be honored.
    const dom = mount('> [!warning] a\n\n> [!tip] b')
    const classes = lineClasses(dom)
    expect(classes[0]).toContain('cm-md-callout-warning')
    expect(classes[0]).not.toContain('cm-md-callout-tip')
    expect(classes[2]).toContain('cm-md-callout-tip')
    expect(classes[2]).not.toContain('cm-md-callout-warning')
  })

  it('a marker-shaped line inside an open quote is body text (parity with rendered pipelines)', () => {
    // `> [!note]` / `> [!caution]` / `> body` with no blank line is ONE
    // blockquote; the rendered pipelines read only its opening, so the second
    // marker is literal body text there. The editor must agree: one note
    // callout throughout, no caution restart, no dim-marker on line 2.
    const dom = mount('> [!note]\n> [!caution]\n> body')
    const classes = lineClasses(dom)
    expect(classes[0]).toContain('cm-md-callout-note')
    expect(classes[1]).toContain('cm-md-callout-note')
    expect(classes[2]).toContain('cm-md-callout-note')
    expect(dom.querySelector('[class*="cm-md-callout-caution"]')).toBeNull()
    const markers = dom.querySelectorAll('.cm-md-callout-marker')
    expect(markers).toHaveLength(1)
    expect(markers[0].textContent).toBe('[!note]')
  })

  it('a marker after a plain quote line is body text, not a callout', () => {
    // The case that distinguishes the quote-opener gate from a naive
    // "no active callout" check: `> plain` / `> [!note]` is one blockquote
    // whose opening has no marker — the rendered pipelines show a plain
    // quote, so the editor must too.
    const dom = mount('> plain\n> [!note] later')
    expect(dom.querySelector('[class*="cm-md-callout"]')).toBeNull()
  })

  it('unknown keywords render as a plain blockquote', () => {
    const dom = mount('> [!FOO] nope')
    expect(lineClasses(dom)[0]).toContain('cm-md-blockquote')
    expect(dom.querySelector('[class*="cm-md-callout"]')).toBeNull()
  })

  it('markers inside fenced code blocks are ignored', () => {
    const dom = mount('```\n> [!warning] not a callout\n```')
    expect(dom.querySelector('[class*="cm-md-callout"]')).toBeNull()
  })

  it('parseLine surfaces the variant and marker span for blockquote lines', () => {
    expect(parseLine('> [!Danger] x', false)).toMatchObject({
      type: 'blockquote',
      callout: 'caution',
      calloutMarker: { from: 2, to: 11 },
    })
    expect(parseLine('> quote', false)).toEqual({ type: 'blockquote' })
  })
})
