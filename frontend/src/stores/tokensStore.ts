/**
 * Zustand store for personal access tokens (PATs).
 * Manages token CRUD operations for the Settings page.
 */
import { create } from 'zustand'
import { api } from '../services/api'
import type { Token, TokenCreate, TokenCreateResponse } from '../types'

interface TokensState {
  tokens: Token[]
  isLoading: boolean
  error: string | null
}

interface TokensActions {
  fetchTokens: () => Promise<void>
  createToken: (data: TokenCreate) => Promise<TokenCreateResponse>
  deleteToken: (id: number) => Promise<void>
  clearError: () => void
}

type TokensStore = TokensState & TokensActions

export const useTokensStore = create<TokensStore>((set, get) => ({
  // State
  tokens: [],
  isLoading: false,
  error: null,

  // Actions
  fetchTokens: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.get<Token[]>('/tokens/')
      set({ tokens: response.data, isLoading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tokens'
      set({ isLoading: false, error: message })
    }
  },

  createToken: async (data: TokenCreate) => {
    const response = await api.post<TokenCreateResponse>('/tokens/', data)
    const newToken = response.data
    // Add to list (without the plaintext token field)
    const tokenForList: Token = {
      id: newToken.id,
      name: newToken.name,
      token_prefix: newToken.token_prefix,
      last_used_at: newToken.last_used_at,
      expires_at: newToken.expires_at,
      created_at: newToken.created_at,
    }
    set({ tokens: [...get().tokens, tokenForList] })
    return newToken
  },

  deleteToken: async (id: number) => {
    await api.delete(`/tokens/${id}`)
    set({ tokens: get().tokens.filter((token) => token.id !== id) })
  },

  clearError: () => {
    set({ error: null })
  },
}))
