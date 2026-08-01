/**
 * Data-fetching hooks for the public (no-auth) read view.
 *
 * Each hook fetches a shared item by its public token via `publicApi` — the
 * axios instance with NO auth interceptor — so a logged-out visitor can read
 * the page without a signed-in session. A 404 (unknown/unpublished/deleted token)
 * surfaces as the query's error state and is NOT retried (it's deterministic);
 * transient failures (network / 5xx / 429 from the IP rate limiter) get a couple
 * of retries. The shell distinguishes these so a transient failure isn't shown
 * as "the owner stopped sharing".
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import axios from 'axios'
import { publicApi } from '../services/api'
import type { PublicBookmark, PublicNote, PublicPrompt } from '../types'

type PublicItemType = 'bookmarks' | 'notes' | 'prompts'

async function fetchPublicItem<T>(type: PublicItemType, token: string): Promise<T> {
  const response = await publicApi.get<T>(`/public/${type}/${token}`)
  return response.data
}

function usePublicItem<T>(
  type: PublicItemType,
  token: string | undefined
): UseQueryResult<T> {
  return useQuery({
    queryKey: ['public', type, token],
    queryFn: () => fetchPublicItem<T>(type, token!),
    enabled: !!token,
    retry: (failureCount, error) => {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined
      if (status === 404) return false // deterministic "gone" — don't retry
      return failureCount < 2 // give transient failures a couple of attempts
    },
  })
}

/** Fetch a shared bookmark by its public token. */
export function usePublicBookmark(token: string | undefined): UseQueryResult<PublicBookmark> {
  return usePublicItem<PublicBookmark>('bookmarks', token)
}

/** Fetch a shared note by its public token. */
export function usePublicNote(token: string | undefined): UseQueryResult<PublicNote> {
  return usePublicItem<PublicNote>('notes', token)
}

/** Fetch a shared prompt by its public token. */
export function usePublicPrompt(token: string | undefined): UseQueryResult<PublicPrompt> {
  return usePublicItem<PublicPrompt>('prompts', token)
}
