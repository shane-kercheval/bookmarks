/**
 * Tag input component with autocomplete suggestions.
 */
import { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react'
import type { ReactNode, KeyboardEvent, ChangeEvent, Ref } from 'react'
import type { TagCount } from '../types'
import { validateTag } from '../utils'

interface TagInputProps {
  /** Currently selected tags */
  value: string[]
  /** Called when tags change */
  onChange: (tags: string[]) => void
  /** Available tags for suggestions */
  suggestions: TagCount[]
  /** Placeholder text */
  placeholder?: string
  /** Whether the input is disabled */
  disabled?: boolean
  /** ID for the input element */
  id?: string
  /** Error message to display */
  error?: string
}

/** Exposed methods via ref */
export interface TagInputHandle {
  /** Get pending text that hasn't been added as a tag yet */
  getPendingValue: () => string
  /** Clear the pending input */
  clearPending: () => void
}

/**
 * TagInput component with autocomplete and chip display.
 *
 * Features:
 * - Type to filter suggestions
 * - Click or Enter to select a suggestion
 * - Type a new tag and press Enter or comma to add it
 * - Click X on chips to remove tags
 * - Tab to select first suggestion
 * - Exposes addPendingTag() via ref for form submission
 */
export const TagInput = forwardRef(function TagInput(
  {
    value,
    onChange,
    suggestions,
    placeholder = 'Add tags...',
    disabled = false,
    id,
    error,
  }: TagInputProps,
  ref: Ref<TagInputHandle>
): ReactNode {
  const [inputValue, setInputValue] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [localError, setLocalError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Filter suggestions based on input and exclude already selected tags
  const filteredSuggestions = suggestions.filter(
    (suggestion) =>
      !value.includes(suggestion.name) &&
      suggestion.name.toLowerCase().includes(inputValue.toLowerCase())
  )

  // Close suggestions when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
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

  const addTag = (tag: string): boolean => {
    const normalized = tag.toLowerCase().trim()
    if (!normalized) return false

    const validationError = validateTag(normalized)

    if (validationError) {
      setLocalError(validationError)
      return false
    }

    if (!value.includes(normalized)) {
      onChange([...value, normalized])
    }

    setInputValue('')
    setLocalError(null)
    setShowSuggestions(false)
    setHighlightedIndex(-1)
    return true
  }

  // Expose methods via ref for form submission
  useImperativeHandle(ref, () => ({
    getPendingValue: () => inputValue.trim(),
    clearPending: () => setInputValue(''),
  }))

  const removeTag = (tagToRemove: string): void => {
    onChange(value.filter((tag) => tag !== tagToRemove))
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const newValue = e.target.value
    setInputValue(newValue)
    setLocalError(null)
    setShowSuggestions(newValue.length > 0 || filteredSuggestions.length > 0)
    setHighlightedIndex(-1)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()

      if (highlightedIndex >= 0 && highlightedIndex < filteredSuggestions.length) {
        // Select highlighted suggestion
        addTag(filteredSuggestions[highlightedIndex].name)
      } else if (inputValue.trim()) {
        // Add typed value as new tag
        addTag(inputValue)
      }
    } else if (e.key === 'Tab' && showSuggestions && filteredSuggestions.length > 0) {
      e.preventDefault()
      // Select first suggestion on Tab
      addTag(filteredSuggestions[0].name)
    } else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
      // Remove last tag on backspace when input is empty
      removeTag(value[value.length - 1])
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
    }
  }

  const displayError = error || localError

  return (
    <div ref={containerRef} className="relative">
      {/* Selected tags and input */}
      <div
        className={`flex min-h-[42px] flex-wrap gap-1.5 rounded-md border bg-white px-3 py-2 ${
          displayError
            ? 'border-red-300 focus-within:border-red-500 focus-within:ring-red-500'
            : 'border-gray-300 focus-within:border-blue-500 focus-within:ring-blue-500'
        } focus-within:ring-1`}
        onClick={() => inputRef.current?.focus()}
      >
        {/* Tag chips */}
        {value.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-sm font-medium text-blue-800"
          >
            {tag}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                removeTag(tag)
              }}
              disabled={disabled}
              className="rounded-full p-0.5 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label={`Remove tag ${tag}`}
            >
              <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          </span>
        ))}

        {/* Input */}
        <input
          ref={inputRef}
          id={id}
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() =>
            setShowSuggestions(
              inputValue.length > 0 || filteredSuggestions.length > 0
            )
          }
          placeholder={value.length === 0 ? placeholder : ''}
          disabled={disabled}
          className="min-w-[100px] flex-1 border-none bg-transparent p-0 text-sm outline-none placeholder:text-gray-400"
        />
      </div>

      {/* Error message */}
      {displayError && (
        <p className="mt-1 text-sm text-red-600">{displayError}</p>
      )}

      {/* Suggestions dropdown */}
      {showSuggestions && filteredSuggestions.length > 0 && (
        <div className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-gray-200 bg-white py-1 shadow-lg">
          {filteredSuggestions.map((suggestion, index) => (
            <button
              key={suggestion.name}
              type="button"
              onClick={() => addTag(suggestion.name)}
              className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${
                index === highlightedIndex
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              <span>{suggestion.name}</span>
              <span className="text-xs text-gray-400">{suggestion.count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
})
