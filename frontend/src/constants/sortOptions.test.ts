/**
 * Tests for sortOptions constants.
 *
 * Tests the sort option definitions and helper functions.
 */
import { describe, it, expect } from 'vitest'
import {
  BASE_SORT_OPTIONS,
  ARCHIVED_SORT_OPTIONS,
  TRASH_SORT_OPTIONS,
  ALL_SORT_OPTIONS,
  SORT_LABELS,
  VIEW_DEFAULTS,
  GLOBAL_DEFAULT,
  getAvailableSortOptions,
  getViewDefault,
} from './sortOptions'

describe('sort option constants', () => {
  describe('BASE_SORT_OPTIONS', () => {
    it('contains the four base sort options', () => {
      expect(BASE_SORT_OPTIONS).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
      ])
    })

    it('does not contain archived_at or deleted_at', () => {
      expect(BASE_SORT_OPTIONS).not.toContain('archived_at')
      expect(BASE_SORT_OPTIONS).not.toContain('deleted_at')
    })
  })

  describe('ARCHIVED_SORT_OPTIONS', () => {
    it('contains base options plus archived_at', () => {
      expect(ARCHIVED_SORT_OPTIONS).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
        'archived_at',
      ])
    })

    it('does not contain deleted_at', () => {
      expect(ARCHIVED_SORT_OPTIONS).not.toContain('deleted_at')
    })
  })

  describe('TRASH_SORT_OPTIONS', () => {
    it('contains base options plus deleted_at', () => {
      expect(TRASH_SORT_OPTIONS).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
        'deleted_at',
      ])
    })

    it('does not contain archived_at', () => {
      expect(TRASH_SORT_OPTIONS).not.toContain('archived_at')
    })
  })

  describe('ALL_SORT_OPTIONS', () => {
    it('contains all six sort options', () => {
      expect(ALL_SORT_OPTIONS).toEqual([
        'last_used_at',
        'created_at',
        'updated_at',
        'title',
        'archived_at',
        'deleted_at',
      ])
    })
  })

  describe('SORT_LABELS', () => {
    it('has labels for all sort options', () => {
      expect(SORT_LABELS.last_used_at).toBe('Last Used')
      expect(SORT_LABELS.created_at).toBe('Date Added')
      expect(SORT_LABELS.updated_at).toBe('Date Modified')
      expect(SORT_LABELS.title).toBe('Title')
      expect(SORT_LABELS.archived_at).toBe('Archived At')
      expect(SORT_LABELS.deleted_at).toBe('Deleted At')
    })

    it('has exactly six labels', () => {
      expect(Object.keys(SORT_LABELS)).toHaveLength(6)
    })
  })

  describe('VIEW_DEFAULTS', () => {
    it('has default for all view', () => {
      expect(VIEW_DEFAULTS.all).toEqual({
        sortBy: 'last_used_at',
        sortOrder: 'desc',
      })
    })

    it('has default for archived view', () => {
      expect(VIEW_DEFAULTS.archived).toEqual({
        sortBy: 'archived_at',
        sortOrder: 'desc',
      })
    })

    it('has default for trash view', () => {
      expect(VIEW_DEFAULTS.trash).toEqual({
        sortBy: 'deleted_at',
        sortOrder: 'desc',
      })
    })

    it('has exactly three view defaults', () => {
      expect(Object.keys(VIEW_DEFAULTS)).toHaveLength(3)
    })
  })

  describe('GLOBAL_DEFAULT', () => {
    it('is last_used_at desc', () => {
      expect(GLOBAL_DEFAULT).toEqual({
        sortBy: 'last_used_at',
        sortOrder: 'desc',
      })
    })
  })
})

describe('getAvailableSortOptions', () => {
  it('returns base options for active view', () => {
    const options = getAvailableSortOptions('active')
    expect(options).toEqual(BASE_SORT_OPTIONS)
  })

  it('returns archived options for archived view', () => {
    const options = getAvailableSortOptions('archived')
    expect(options).toEqual(ARCHIVED_SORT_OPTIONS)
  })

  it('returns trash options for deleted view', () => {
    const options = getAvailableSortOptions('deleted')
    expect(options).toEqual(TRASH_SORT_OPTIONS)
  })
})

describe('getViewDefault', () => {
  it('returns all view default for "all" key', () => {
    const result = getViewDefault('all')
    expect(result).toEqual(VIEW_DEFAULTS.all)
  })

  it('returns archived view default for "archived" key', () => {
    const result = getViewDefault('archived')
    expect(result).toEqual(VIEW_DEFAULTS.archived)
  })

  it('returns trash view default for "trash" key', () => {
    const result = getViewDefault('trash')
    expect(result).toEqual(VIEW_DEFAULTS.trash)
  })

  it('returns global default for custom list keys', () => {
    const result = getViewDefault('list:5')
    expect(result).toEqual(GLOBAL_DEFAULT)
  })

  it('returns global default for unknown keys', () => {
    const result = getViewDefault('unknown')
    expect(result).toEqual(GLOBAL_DEFAULT)
  })
})
