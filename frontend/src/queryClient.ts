import { QueryClient } from '@tanstack/react-query'

/**
 * TanStack Query client with application-wide defaults.
 *
 * Configuration:
 * - staleTime: 20 minutes - data considered fresh, won't refetch
 * - gcTime: 30 minutes - keep unused data in cache
 * - retry: 1 - single retry on failure
 * - refetchOnWindowFocus: false - disabled because common flow is click bookmark,
 *   read content, come back. Mutations invalidate cache for same-tab edits.
 *   Multi-tab editing is rare; users can refresh manually if needed.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 20,       // 20 minutes
      gcTime: 1000 * 60 * 30,          // 30 minutes
      retry: 1,
      refetchOnWindowFocus: false,     // Disable - common flow is click bookmark, read, come back
    },
  },
})

/**
 * Create a fresh QueryClient for testing.
 * Disables retries to make tests faster and more predictable.
 */
export const createTestQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
