/**
 * Settings page for Personal Access Token management.
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { useTokensStore } from '../../stores/tokensStore'
import { TokenList } from '../../components/TokenList'
import { CreateTokenModal } from '../../components/CreateTokenModal'
import type { TokenCreate, TokenCreateResponse } from '../../types'

/**
 * Personal Access Tokens settings page.
 */
export function SettingsTokens(): ReactNode {
  const { tokens, isLoading, fetchTokens, createToken, deleteToken } = useTokensStore()

  // Modal state
  const [showCreateToken, setShowCreateToken] = useState(false)

  // Fetch data on mount
  useEffect(() => {
    fetchTokens()
  }, [fetchTokens])

  // Token handlers
  const handleCreateToken = async (data: TokenCreate): Promise<TokenCreateResponse> => {
    const response = await createToken(data)
    toast.success(`Token "${data.name}" created`)
    return response
  }

  const handleDeleteToken = async (id: number): Promise<void> => {
    try {
      await deleteToken(id)
      toast.success('Token deleted')
    } catch {
      toast.error('Failed to delete token')
      throw new Error('Failed to delete token')
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Personal Access Tokens</h1>
        <p className="mt-1 text-gray-500">
          Create tokens for API access. Tokens are shown only once when created.
        </p>
      </div>

      <TokenList
        tokens={tokens}
        isLoading={isLoading}
        onDelete={handleDeleteToken}
        onCreateClick={() => setShowCreateToken(true)}
      />

      {/* Create Token Modal */}
      <CreateTokenModal
        isOpen={showCreateToken}
        onClose={() => setShowCreateToken(false)}
        onCreate={handleCreateToken}
      />
    </div>
  )
}
