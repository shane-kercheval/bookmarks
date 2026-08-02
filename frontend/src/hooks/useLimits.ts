/**
 * Hook for fetching and caching user tier limits.
 *
 * Limits are fetched from /users/me/limits and cached indefinitely
 * (staleTime: Infinity) since they rarely change. A page refresh
 * clears the cache and fetches fresh limits.
 *
 * The cache is scoped by user ID to prevent stale limits when switching
 * accounts without a full page reload.
 */
import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import { useAuthStatus } from './useAuthStatus'
import type { UserLimits } from '../types'

/**
 * Query key factory for user limits.
 * Scoped by user ID to handle account switching.
 */
export const limitsKeys = {
  all: ['user-limits'] as const,
  user: (userId: string) => [...limitsKeys.all, userId] as const,
}

/**
 * Permissive limits for the public read-only view.
 *
 * `useLimits` only fetches for authenticated users (gated on auth below), and
 * tier limits only constrain *editing* — which the public view disables. Without
 * a fallback, the reused detail components (which block rendering until `limits`
 * is present) would spin forever for a logged-out visitor. They use this instead.
 */
const UNBOUNDED = Number.MAX_SAFE_INTEGER
export const PUBLIC_VIEW_LIMITS: UserLimits = {
  tier: 'public',
  max_bookmarks: UNBOUNDED,
  max_notes: UNBOUNDED,
  max_prompts: UNBOUNDED,
  max_pats: UNBOUNDED,
  max_title_length: UNBOUNDED,
  max_description_length: UNBOUNDED,
  max_tag_name_length: UNBOUNDED,
  max_bookmark_content_length: UNBOUNDED,
  max_note_content_length: UNBOUNDED,
  max_prompt_content_length: UNBOUNDED,
  max_url_length: UNBOUNDED,
  max_prompt_name_length: UNBOUNDED,
  max_argument_name_length: UNBOUNDED,
  max_argument_description_length: UNBOUNDED,
  rate_read_per_minute: UNBOUNDED,
  rate_read_per_day: UNBOUNDED,
  rate_write_per_minute: UNBOUNDED,
  rate_write_per_day: UNBOUNDED,
  rate_sensitive_per_minute: UNBOUNDED,
  rate_sensitive_per_day: UNBOUNDED,
  rate_ai_per_minute: UNBOUNDED,
  rate_ai_per_day: UNBOUNDED,
  rate_ai_byok_per_minute: UNBOUNDED,
  rate_ai_byok_per_day: UNBOUNDED,
  max_relationships_per_entity: UNBOUNDED,
  history_retention_days: UNBOUNDED,
  max_history_per_entity: UNBOUNDED,
}

/**
 * Fetch user limits from API.
 */
async function fetchLimits(): Promise<UserLimits> {
  const response = await api.get<UserLimits>('/users/me/limits')
  return response.data
}

/**
 * Hook for fetching user tier limits with caching.
 *
 * @returns Query result with limits data, loading state, and error
 *
 * @example
 * ```tsx
 * const { limits, isLoading, error } = useLimits()
 *
 * if (error) {
 *   return <ErrorBanner message="Failed to load limits" />
 * }
 * if (isLoading || !limits) {
 *   return <LoadingSpinner />
 * }
 *
 * return <Input maxLength={limits.max_title_length} />
 * ```
 */
export function useLimits(): {
  limits: UserLimits | undefined
  isLoading: boolean
  error: Error | null
} {
  const { isAuthenticated, userId } = useAuthStatus()

  const { data, isLoading, error } = useQuery({
    queryKey: limitsKeys.user(userId ?? 'anonymous'),
    queryFn: fetchLimits,
    enabled: isAuthenticated && !!userId,
    staleTime: Infinity, // Limits rarely change, cache until page refresh
    gcTime: Infinity, // Keep in cache indefinitely
  })

  return {
    limits: data,
    isLoading,
    error: error as Error | null,
  }
}
