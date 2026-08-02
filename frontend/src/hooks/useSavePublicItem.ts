/**
 * Mutation hook for "Save a copy" on the public read view.
 *
 * POSTs to the authenticated clone endpoint (`POST /public/{type}/{token}/save`)
 * via the shared `api` instance — this call REQUIRES a token (the clone is
 * written into the caller's account), so unlike the public reads it goes through
 * the authed client, not `publicApi`. On success it invalidates the relevant
 * list caches and navigates to the freshly created item.
 */
import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import toast from 'react-hot-toast'
import { api, GLOBALLY_TOASTED_STATUSES } from '../services/api'
import { getApiErrorMessage } from '../utils'

type PublicItemType = 'bookmarks' | 'notes' | 'prompts'

interface ClonedItem {
  id: string
}

/**
 * @param type  Content type of the shared item.
 * @param token Public share token from the URL.
 */
export function useSavePublicItem(
  type: PublicItemType,
  token: string
): UseMutationResult<ClonedItem, unknown, void> {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  return useMutation<ClonedItem, unknown, void>({
    mutationFn: async () => {
      const response = await api.post<ClonedItem>(`/public/${type}/${token}/save`)
      return response.data
    },
    onSuccess: (item) => {
      // Surface the new copy in list/content views, then jump to it.
      queryClient.invalidateQueries({ queryKey: [type] })
      queryClient.invalidateQueries({ queryKey: ['content'] })
      navigate(`/app/${type}/${item.id}`)
    },
    onError: (error: unknown) => {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined

      // The shared response interceptor already toasts 402 (quota) and 429
      // (rate limit); avoid double-toasting those. Everything else (e.g. a 409
      // name/URL conflict) gets a descriptive toast here.
      if (status && (GLOBALLY_TOASTED_STATUSES as readonly number[]).includes(status)) {
        return
      }
      toast.error(getApiErrorMessage(error, 'Failed to save a copy'))
    },
  })
}
