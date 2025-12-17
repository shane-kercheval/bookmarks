/**
 * Modal for creating a new personal access token.
 */
import { useState, useEffect, useRef } from 'react'
import type { ReactNode, FormEvent } from 'react'
import type { TokenCreate, TokenCreateResponse } from '../types'
import { CopyIcon, CheckIcon } from './icons'
import { Modal } from './ui/Modal'
import { config } from '../config'

interface CreateTokenModalProps {
  isOpen: boolean
  onClose: () => void
  onCreate: (data: TokenCreate) => Promise<TokenCreateResponse>
}

/** Expiry options in days */
const EXPIRY_OPTIONS = [
  { value: '', label: 'Never' },
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: '1 year' },
]

/**
 * Modal for creating tokens with reveal functionality.
 */
export function CreateTokenModal({ isOpen, onClose, onCreate }: CreateTokenModalProps): ReactNode {
  const [name, setName] = useState('')
  const [expiresInDays, setExpiresInDays] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdToken, setCreatedToken] = useState<TokenCreateResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const [copiedCurl, setCopiedCurl] = useState(false)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const tokenInputRef = useRef<HTMLInputElement>(null)

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setName('')
      setExpiresInDays('')
      setError(null)
      setCreatedToken(null)
      setCopied(false)
      setCopiedCurl(false)
      // Focus name input after a short delay to ensure modal is rendered
      setTimeout(() => nameInputRef.current?.focus(), 100)
    }
  }, [isOpen])

  const handleSubmit = async (e: FormEvent): Promise<void> => {
    e.preventDefault()

    if (!name.trim()) {
      setError('Token name is required')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      const data: TokenCreate = {
        name: name.trim(),
        expires_in_days: expiresInDays ? parseInt(expiresInDays, 10) : undefined,
      }
      const response = await onCreate(data)
      setCreatedToken(response)
      // Select the token text for easy copying
      setTimeout(() => {
        tokenInputRef.current?.select()
      }, 100)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create token')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCopy = async (): Promise<void> => {
    if (!createdToken) return

    try {
      await navigator.clipboard.writeText(createdToken.token)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback to selecting text
      tokenInputRef.current?.select()
    }
  }

  const getCurlCommand = (token: string): string => {
    return `curl -H "Authorization: Bearer ${token}" ${config.apiUrl}/bookmarks/`
  }

  const handleCopyCurl = async (): Promise<void> => {
    if (!createdToken) return

    try {
      await navigator.clipboard.writeText(getCurlCommand(createdToken.token))
      setCopiedCurl(true)
      setTimeout(() => setCopiedCurl(false), 2000)
    } catch {
      // Silent fail
    }
  }

  const handleClose = (): void => {
    // Warn user if they haven't copied the token
    if (createdToken && !copied) {
      if (!confirm('Have you copied the token? It will not be shown again.')) {
        return
      }
    }
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={createdToken ? 'Token Created' : 'Create Token'}
      maxWidth="max-w-md"
    >
      {createdToken ? (
        // Token reveal view
        <div className="space-y-4">
          <div className="rounded-lg bg-yellow-50 border border-yellow-200 p-3">
            <p className="text-sm text-yellow-800">
              Make sure to copy your token now. You won't be able to see it again!
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Your Token
            </label>
            <div className="flex gap-2">
              <input
                ref={tokenInputRef}
                type="text"
                value={createdToken.token}
                readOnly
                className="input font-mono text-sm flex-1"
              />
              <button
                onClick={handleCopy}
                className={`btn-secondary inline-flex items-center gap-1.5 ${
                  copied ? 'text-green-600' : ''
                }`}
              >
                {copied ? <CheckIcon /> : <CopyIcon />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Example Usage
            </label>
            <div className="relative">
              <pre className="rounded-lg bg-gray-900 p-3 text-sm text-gray-100 overflow-x-auto">
                <code>{getCurlCommand(createdToken.token)}</code>
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
          </div>

          <div className="pt-2">
            <button onClick={handleClose} className="btn-primary w-full">
              Done
            </button>
          </div>
        </div>
      ) : (
        // Create form view
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <div>
            <label htmlFor="token-name" className="block text-sm font-medium text-gray-700 mb-1">
              Token Name
            </label>
            <input
              ref={nameInputRef}
              id="token-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., CLI access, Automation script"
              className="input"
              disabled={isSubmitting}
            />
            <p className="mt-1 text-xs text-gray-500">
              A descriptive name to help you identify this token.
            </p>
          </div>

          <div>
            <label htmlFor="token-expiry" className="block text-sm font-medium text-gray-700 mb-1">
              Expiration
            </label>
            <select
              id="token-expiry"
              value={expiresInDays}
              onChange={(e) => setExpiresInDays(e.target.value)}
              className="input"
              disabled={isSubmitting}
            >
              {EXPIRY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="btn-secondary flex-1"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary flex-1"
              disabled={isSubmitting || !name.trim()}
            >
              {isSubmitting ? 'Creating...' : 'Create Token'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}
