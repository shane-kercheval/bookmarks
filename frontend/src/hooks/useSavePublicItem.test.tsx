/**
 * Tests for the "Save a copy" mutation hook.
 *
 * The clone POST goes through the authed `api` instance (it writes into the
 * caller's account); on success it invalidates list caches and navigates to the
 * new item; on error it toasts — except for statuses the shared interceptor
 * already toasts (402 quota, 429 rate limit).
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { useSavePublicItem } from './useSavePublicItem'
import { api } from '../services/api'

const mockNavigate = vi.fn()

vi.mock('../services/api', () => ({
  api: { post: vi.fn() },
  GLOBALLY_TOASTED_STATUSES: [402, 429],
}))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }))
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})
vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      isAxiosError: (e: unknown) => !!(e as { isAxiosError?: boolean })?.isAxiosError,
    },
  }
})

const mockPost = api.post as Mock
const mockToastError = toast.error as Mock

let queryClient: QueryClient
function wrapper({ children }: { children: ReactNode }): ReactNode {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

describe('useSavePublicItem', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
  })

  it('POSTs to the clone endpoint and navigates to the new item on success', async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 'new-id' } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useSavePublicItem('notes', 'tok'), { wrapper })
    await act(async () => {
      await result.current.mutateAsync()
    })

    expect(mockPost).toHaveBeenCalledWith('/public/notes/tok/save')
    expect(mockNavigate).toHaveBeenCalledWith('/app/notes/new-id')
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['notes'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['content'] })
  })

  it('toasts a descriptive error for a 409 conflict', async () => {
    mockPost.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 409, data: { detail: { message: 'A prompt named X already exists' } } },
    })

    const { result } = renderHook(() => useSavePublicItem('prompts', 'tok'), { wrapper })
    await act(async () => {
      await result.current.mutateAsync().catch(() => {})
    })

    expect(mockToastError).toHaveBeenCalledTimes(1)
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('does not double-toast statuses the interceptor already handles (402 quota)', async () => {
    mockPost.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 402, data: { error_code: 'QUOTA_EXCEEDED' } },
    })

    const { result } = renderHook(() => useSavePublicItem('bookmarks', 'tok'), { wrapper })
    await act(async () => {
      await result.current.mutateAsync().catch(() => {})
    })

    expect(mockToastError).not.toHaveBeenCalled()
  })

})
