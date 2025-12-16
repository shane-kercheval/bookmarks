import { useState, useEffect } from 'react'

/**
 * Hook that debounces a value.
 *
 * Returns the debounced value that only updates after the specified delay
 * has passed without the value changing.
 *
 * @param value - The value to debounce
 * @param delay - Delay in milliseconds (default: 300ms)
 * @returns The debounced value
 *
 * @example
 * ```tsx
 * const [searchQuery, setSearchQuery] = useState('')
 * const debouncedQuery = useDebouncedValue(searchQuery, 300)
 *
 * useEffect(() => {
 *   // This only runs 300ms after user stops typing
 *   fetchResults(debouncedQuery)
 * }, [debouncedQuery])
 * ```
 */
export function useDebouncedValue<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}
