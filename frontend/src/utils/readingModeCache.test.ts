/**
 * Tests for the per-item reading-mode LRU (see readingModeCache.ts).
 *
 * The LRU semantics matter here: reads must refresh recency (an item opened
 * daily but toggled once must not age out), and only reading-mode-ON entries
 * are stored (off = the miss-default, so it carries no information).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  readReadingMode,
  touchReadingMode,
  writeReadingMode,
  clearReadingModeCache,
} from './readingModeCache'

const STORAGE_KEY = 'tiddly:reading-mode'

/** Advance the mocked clock so every write gets a strictly increasing timestamp. */
let clock = 1_000
function tick(): void {
  clock += 1_000
  vi.spyOn(Date, 'now').mockReturnValue(clock)
}

beforeEach(() => {
  localStorage.clear()
  clock = 1_000
  tick()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('readingModeCache — basic behavior', () => {
  it('miss reads as false; write(true) → hit; write(false) deletes the entry', () => {
    expect(readReadingMode('a')).toBe(false)

    writeReadingMode('a', true)
    expect(readReadingMode('a')).toBe(true)

    writeReadingMode('a', false)
    expect(readReadingMode('a')).toBe(false)
    // Off is not stored — the map has no entry at all, not a `false` value.
    expect(localStorage.getItem(STORAGE_KEY)).not.toContain('"a"')
  })

  it('write(false) on a miss is a no-op (does not create storage)', () => {
    writeReadingMode('never-seen', false)
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('touch on a miss does not create an entry', () => {
    touchReadingMode('never-toggled')
    expect(readReadingMode('never-toggled')).toBe(false)
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('clearReadingModeCache removes everything', () => {
    writeReadingMode('a', true)
    writeReadingMode('b', true)
    clearReadingModeCache()
    expect(readReadingMode('a')).toBe(false)
    expect(readReadingMode('b')).toBe(false)
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})

describe('readingModeCache — corrupted or foreign stored data', () => {
  it.each([
    ['unparseable JSON', 'not-json{{{'],
    ['a JSON array', '[1,2,3]'],
    ['a JSON scalar', '42'],
    ['null', 'null'],
  ])('treats %s as empty and stays writable', (_label: string, raw: string) => {
    localStorage.setItem(STORAGE_KEY, raw)
    expect(readReadingMode('a')).toBe(false)

    writeReadingMode('a', true)
    expect(readReadingMode('a')).toBe(true)
  })

  it('drops non-numeric entry values but keeps valid ones', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ good: 5, bad: 'x', worse: null }))
    expect(readReadingMode('good')).toBe(true)
    expect(readReadingMode('bad')).toBe(false)
    expect(readReadingMode('worse')).toBe(false)
  })

  it('swallows storage write errors', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    expect(() => writeReadingMode('a', true)).not.toThrow()
    expect(() => touchReadingMode('a')).not.toThrow()
  })

  it('swallows storage read errors', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })
    expect(readReadingMode('a')).toBe(false)
    expect(() => writeReadingMode('a', true)).not.toThrow()
  })
})

describe('readingModeCache — LRU eviction', () => {
  function fill(prefix: string, count: number): void {
    for (let i = 0; i < count; i++) {
      tick()
      writeReadingMode(`${prefix}${i}`, true)
    }
  }

  it('caps at 100 entries', () => {
    fill('item-', 150)
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, number>
    expect(Object.keys(stored)).toHaveLength(100)
    // The newest 100 survive; the oldest 50 were evicted.
    expect(readReadingMode('item-149')).toBe(true)
    expect(readReadingMode('item-49')).toBe(false)
    expect(readReadingMode('item-50')).toBe(true)
  })

  it('a read-refreshed entry survives; the oldest untouched entry is evicted', () => {
    // The decisive LRU sequence: fill with A plus 99 others (at cap), refresh A
    // by touching it, insert ONE new entry → A survives and the oldest
    // UNTOUCHED entry (other-0) is evicted. (Note: "touch A then insert 100
    // more" would correctly evict A — that is not a valid survival test.)
    tick()
    writeReadingMode('A', true)
    fill('other-', 99)

    tick()
    touchReadingMode('A')
    tick()
    writeReadingMode('new-entry', true)

    expect(readReadingMode('A')).toBe(true)
    expect(readReadingMode('new-entry')).toBe(true)
    expect(readReadingMode('other-0')).toBe(false)
    expect(readReadingMode('other-1')).toBe(true)
  })

  it('without the read refresh, the same sequence evicts A (recency is real, not insertion order)', () => {
    tick()
    writeReadingMode('A', true)
    fill('other-', 99)

    tick()
    writeReadingMode('new-entry', true)

    expect(readReadingMode('A')).toBe(false)
    expect(readReadingMode('other-0')).toBe(true)
  })

  it('re-writing an existing entry refreshes it without evicting anyone', () => {
    tick()
    writeReadingMode('A', true)
    fill('other-', 99) // at cap: A + 99

    tick()
    writeReadingMode('A', true) // already present — refresh, no eviction needed

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, number>
    expect(Object.keys(stored)).toHaveLength(100)
    expect(readReadingMode('A')).toBe(true)
    expect(readReadingMode('other-0')).toBe(true)
  })

  it('toggle-off then re-toggle-on reinserts with fresh recency', () => {
    tick()
    writeReadingMode('A', true)
    tick()
    writeReadingMode('A', false)
    expect(readReadingMode('A')).toBe(false)

    tick()
    writeReadingMode('A', true)
    expect(readReadingMode('A')).toBe(true)
  })
})
