/**
 * Per-item reading-mode memory — a small localStorage-backed LRU.
 *
 * Reading mode used to be transient component state, silently reset by any
 * editor remount (page refresh, conflict refresh, version restore, bookmark
 * content fetch). It is deliberately NOT a global preference like wrap/line
 * numbers/mono font: a global would leak one item's mode to all items (opening
 * the create view as a blank read-only preview) and would regress prompts,
 * which intentionally default to raw source. So: remembered per item.
 *
 * Storage shape — one key holding `{ [itemId]: lastUsedMs }`:
 * - Only items with reading mode ON are stored. "Off" is indistinguishable from
 *   the miss-default (markdown), so storing it would carry no information; the
 *   cap therefore bounds only meaningful overrides.
 * - The timestamp doubles as LRU recency. Both reads (opening an item in
 *   reading mode) and writes refresh it — read-refresh matters because an item
 *   the user *opens* daily but toggled only once must not age out.
 * - The cap (100) is a runaway guard, not a UX mechanism: it's sized so
 *   eviction effectively never fires in normal use, because an eviction here is
 *   a visible behavior change ("this note used to open rendered") with an
 *   invisible cause. ~50 bytes/entry makes the cap generosity, not necessity.
 *
 * Like the draft keys (see drafts.ts), entries are not namespaced by user;
 * account deletion clears the whole cache via clearReadingModeCache(), invoked
 * as a discrete teardown step in AuthProvider (NOT via clearAllDrafts, which is
 * prefix-scoped to draft keys).
 */

const STORAGE_KEY = 'tiddly:reading-mode'

const MAX_ENTRIES = 100

type CacheMap = Record<string, number>

/** Load the map, treating missing/corrupted/foreign-shaped data as empty. */
function loadMap(): CacheMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === null) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const map: CacheMap = {}
    for (const [id, ts] of Object.entries(parsed)) {
      if (typeof ts === 'number' && Number.isFinite(ts)) {
        map[id] = ts
      }
    }
    return map
  } catch {
    return {}
  }
}

function saveMap(map: CacheMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  } catch {
    // Storage unavailable/full — reading-mode memory is best-effort.
  }
}

/** Whether the item was last left in reading mode. Pure read (no recency touch). */
export function readReadingMode(itemId: string): boolean {
  return loadMap()[itemId] !== undefined
}

/**
 * Refresh an existing entry's recency (no-op on miss — a touch must never
 * *create* an entry, or every opened item would count as reading-mode-on).
 */
export function touchReadingMode(itemId: string): void {
  const map = loadMap()
  if (map[itemId] === undefined) return
  map[itemId] = Date.now()
  saveMap(map)
}

/** Persist a toggle: on → insert/refresh (evicting LRU past the cap), off → delete. */
export function writeReadingMode(itemId: string, on: boolean): void {
  const map = loadMap()
  if (!on) {
    if (map[itemId] === undefined) return
    delete map[itemId]
    saveMap(map)
    return
  }
  if (map[itemId] === undefined) {
    const ids = Object.keys(map)
    if (ids.length >= MAX_ENTRIES) {
      ids.sort((a, b) => map[a] - map[b])
      for (const evict of ids.slice(0, ids.length - (MAX_ENTRIES - 1))) {
        delete map[evict]
      }
    }
  }
  map[itemId] = Date.now()
  saveMap(map)
}

/** Remove the whole cache. Account-deletion teardown (see AuthProvider). */
export function clearReadingModeCache(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Best-effort, mirroring clearAllDrafts — must never throw out of teardown.
  }
}
