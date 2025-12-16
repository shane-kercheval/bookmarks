/**
 * Compact tag filter input with autocomplete for filtering bookmarks by tags.
 */
import { useState, useRef, useEffect } from 'react'
import type { ReactNode, KeyboardEvent, ChangeEvent } from 'react'
import type { TagCount } from '../types'

interface TagFilterInputProps {
  /** Available tags for suggestions */
  suggestions: TagCount[]
  /** Tags already selected (to exclude from suggestions) */
  selectedTags: string[]
  /** Called when a tag is selected */
  onTagSelect: (tag: string) => void
  /** Placeholder text */
  placeholder?: string
  /** Whether the input is disabled */
  disabled?: boolean
}

/** Tag icon SVG */
const TagIcon = (): ReactNode => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
    />
  </svg>
)

/**
 * TagFilterInput - compact autocomplete input for filtering by tags.
 *
 * Features:
 * - Type to filter available tags
 * - Click or Enter to select
 * - Arrow keys for navigation
 * - Excludes already-selected tags from suggestions
 */
export function TagFilterInput({
  suggestions,
  selectedTags,
  onTagSelect,
  placeholder = 'Filter by tag...',
  disabled = false,
}: TagFilterInputProps): ReactNode {
  const [inputValue, setInputValue] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Filter suggestions based on input and exclude already selected tags
  const filteredSuggestions = suggestions.filter(
    (suggestion) =>
      !selectedTags.includes(suggestion.name) &&
      suggestion.name.toLowerCase().includes(inputValue.toLowerCase())
  )

  // Close suggestions when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectTag = (tag: string): void => {
    onTagSelect(tag)
    setInputValue('')
    setShowSuggestions(false)
    setHighlightedIndex(-1)
    // Keep focus on input for quick multi-select
    inputRef.current?.focus()
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const newValue = e.target.value
    setInputValue(newValue)
    setShowSuggestions(true)
    setHighlightedIndex(-1)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (highlightedIndex >= 0 && highlightedIndex < filteredSuggestions.length) {
        selectTag(filteredSuggestions[highlightedIndex].name)
      } else if (filteredSuggestions.length === 1) {
        // Auto-select if only one match
        selectTag(filteredSuggestions[0].name)
      }
    } else if (e.key === 'Tab' && showSuggestions && filteredSuggestions.length > 0) {
      e.preventDefault()
      selectTag(filteredSuggestions[0].name)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex((prev) =>
        prev < filteredSuggestions.length - 1 ? prev + 1 : prev
      )
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : prev))
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
      setHighlightedIndex(-1)
      inputRef.current?.blur()
    }
  }

  const handleFocus = (): void => {
    setShowSuggestions(true)
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
          <TagIcon />
        </div>
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          placeholder={placeholder}
          disabled={disabled}
          className="w-40 rounded-lg border border-gray-200 bg-gray-50/50 py-2.5 pl-9 pr-3 text-sm placeholder:text-gray-400 focus:border-gray-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-gray-900/5"
        />
      </div>

      {/* Suggestions dropdown */}
      {showSuggestions && filteredSuggestions.length > 0 && (
        <div className="absolute z-10 mt-1.5 max-h-60 w-full overflow-auto rounded-xl border border-gray-100 bg-white py-1 shadow-lg">
          {filteredSuggestions.map((suggestion, index) => (
            <button
              key={suggestion.name}
              type="button"
              onClick={() => selectTag(suggestion.name)}
              aria-selected={index === highlightedIndex}
              className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors ${
                index === highlightedIndex
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              <span>{suggestion.name}</span>
              <span className="text-xs text-gray-400">{suggestion.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* No results message */}
      {showSuggestions && inputValue && filteredSuggestions.length === 0 && (
        <div className="absolute z-10 mt-1.5 w-full rounded-xl border border-gray-100 bg-white py-2 px-3 shadow-lg">
          <p className="text-sm text-gray-400">No matching tags</p>
        </div>
      )}
    </div>
  )
}
