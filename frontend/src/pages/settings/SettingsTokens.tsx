/**
 * Settings page for Personal Access Token management.
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import toast from 'react-hot-toast'
import { useTokensStore } from '../../stores/tokensStore'
import { TokenList } from '../../components/TokenList'
import { CreateTokenModal } from '../../components/CreateTokenModal'
import { config } from '../../config'
import type { TokenCreate, TokenCreateResponse } from '../../types'

const EXAMPLE_CURL = `curl \\
  -H "Authorization: Bearer bm_xxx" \\
  ${config.apiUrl}/bookmarks/`

/**
 * Personal Access Tokens settings page.
 */
export function SettingsTokens(): ReactNode {
  const { tokens, isLoading, fetchTokens, createToken, deleteToken } = useTokensStore()

  // Modal state
  const [showCreateToken, setShowCreateToken] = useState(false)
  const [copiedCurl, setCopiedCurl] = useState(false)

  const handleCopyCurl = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(EXAMPLE_CURL)
      setCopiedCurl(true)
      setTimeout(() => setCopiedCurl(false), 2000)
    } catch {
      // Silent fail
    }
  }

  // Fetch data on mount
  useEffect(() => {
    fetchTokens()
  }, [fetchTokens])

  // Token handlers
  const handleCreateToken = async (data: TokenCreate): Promise<TokenCreateResponse> => {
    const response = await createToken(data)
    return response
  }

  const handleDeleteToken = async (id: number): Promise<void> => {
    try {
      await deleteToken(id)
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

      {/* Example Usage */}
      <div className="mt-8">
        <h2 className="text-sm font-medium text-gray-700 mb-2">Example Usage</h2>
        <div className="relative">
          <pre className="rounded-lg bg-gray-900 p-3 text-sm text-gray-100 whitespace-pre-wrap break-all">
            <code>{EXAMPLE_CURL}</code>
          </pre>
          <button
            onClick={handleCopyCurl}
            className={`absolute top-2 right-2 rounded px-2 py-1 text-xs transition-colors ${
              copiedCurl
                ? 'bg-green-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {copiedCurl ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-500">
          Replace <code className="bg-gray-100 px-1 rounded">bm_xxx</code> with your token.
        </p>
      </div>

      {/* Create Token Modal */}
      <CreateTokenModal
        isOpen={showCreateToken}
        onClose={() => setShowCreateToken(false)}
        onCreate={handleCreateToken}
      />
    </div>
  )
}
