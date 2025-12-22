import { useState, useEffect } from 'react'
import { getPolicyVersions, type PolicyVersions } from '../services/api'

interface UsePolicyVersionsResult {
  versions: PolicyVersions | null
  isLoading: boolean
  error: string | null
  formatVersionDate: (version: string) => string
}

/**
 * Hook to fetch and format policy versions from the API.
 * Used by public policy pages to display version dates.
 */
export function usePolicyVersions(): UsePolicyVersionsResult {
  const [versions, setVersions] = useState<PolicyVersions | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetchVersions(): Promise<void> {
      try {
        const data = await getPolicyVersions()
        if (!cancelled) {
          setVersions(data)
          setIsLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load policy versions')
          setIsLoading(false)
        }
      }
    }

    fetchVersions()

    return () => {
      cancelled = true
    }
  }, [])

  /**
   * Format version date for display (e.g., "2025-12-20" -> "December 20, 2025")
   */
  const formatVersionDate = (version: string): string => {
    const date = new Date(version + 'T00:00:00')
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
  }

  return { versions, isLoading, error, formatVersionDate }
}
