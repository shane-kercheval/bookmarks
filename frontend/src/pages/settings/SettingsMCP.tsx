/**
 * Settings page for MCP (Model Context Protocol) setup instructions.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { config } from '../../config'

const CONFIG_PATH_MAC = '~/Library/Application\\ Support/Claude/claude_desktop_config.json'
const CONFIG_PATH_WINDOWS = '%APPDATA%\\Claude\\claude_desktop_config.json'

/**
 * Generate the Claude Desktop config JSON.
 */
function generateConfig(mcpUrl: string): string {
  const configObj = {
    mcpServers: {
      bookmarks: {
        command: 'npx',
        args: [
          'mcp-remote',
          `${mcpUrl}/mcp`,
          '--header',
          'Authorization: Bearer YOUR_TOKEN_HERE',
        ],
      },
    },
  }
  return JSON.stringify(configObj, null, 2)
}

/**
 * MCP setup instructions settings page.
 */
export function SettingsMCP(): ReactNode {
  const [copiedConfig, setCopiedConfig] = useState(false)
  const [copiedPathMac, setCopiedPathMac] = useState(false)
  const [copiedPathWin, setCopiedPathWin] = useState(false)

  const exampleConfig = generateConfig(config.mcpUrl)

  const handleCopyConfig = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(exampleConfig)
      setCopiedConfig(true)
      setTimeout(() => setCopiedConfig(false), 2000)
    } catch {
      // Silent fail
    }
  }

  const handleCopyPathMac = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(CONFIG_PATH_MAC)
      setCopiedPathMac(true)
      setTimeout(() => setCopiedPathMac(false), 2000)
    } catch {
      // Silent fail
    }
  }

  const handleCopyPathWin = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(CONFIG_PATH_WINDOWS)
      setCopiedPathWin(true)
      setTimeout(() => setCopiedPathWin(false), 2000)
    } catch {
      // Silent fail
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">MCP Integration</h1>
        <p className="mt-1 text-gray-500">
          Connect Claude Desktop to your bookmarks using the Model Context Protocol (MCP).
        </p>
      </div>

      {/* Step 1: Create PAT */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Step 1: Create a Personal Access Token
        </h2>
        <p className="text-gray-600 mb-3">
          You need a Personal Access Token (PAT) to authenticate with the MCP server.
        </p>
        <Link
          to="/settings/tokens"
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Create Token
        </Link>
      </div>

      {/* Step 2: Config file location */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Step 2: Locate Claude Desktop Config
        </h2>
        <p className="text-gray-600 mb-3">
          Create or edit the Claude Desktop configuration file at:
        </p>
        <div className="space-y-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-gray-700">macOS:</span>
            </div>
            <div className="relative">
              <code className="block rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-800 pr-16">
                {CONFIG_PATH_MAC}
              </code>
              <button
                onClick={handleCopyPathMac}
                className={`absolute top-1.5 right-2 rounded px-2 py-1 text-xs transition-colors ${
                  copiedPathMac
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                }`}
              >
                {copiedPathMac ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-gray-700">Windows:</span>
            </div>
            <div className="relative">
              <code className="block rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-800 pr-16">
                {CONFIG_PATH_WINDOWS}
              </code>
              <button
                onClick={handleCopyPathWin}
                className={`absolute top-1.5 right-2 rounded px-2 py-1 text-xs transition-colors ${
                  copiedPathWin
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                }`}
              >
                {copiedPathWin ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Step 3: Add config */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Step 3: Add MCP Server Configuration
        </h2>
        <p className="text-gray-600 mb-3">
          Add the following to your Claude Desktop config file:
        </p>
        <div className="relative">
          <pre className="rounded-lg bg-gray-900 p-3 text-sm text-gray-100 whitespace-pre-wrap break-all overflow-x-auto">
            <code>{exampleConfig}</code>
          </pre>
          <button
            onClick={handleCopyConfig}
            className={`absolute top-2 right-2 rounded px-2 py-1 text-xs transition-colors ${
              copiedConfig
                ? 'bg-green-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {copiedConfig ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="mt-2 text-sm text-gray-500">
          Replace <code className="bg-gray-100 px-1 rounded">YOUR_TOKEN_HERE</code> with your
          Personal Access Token from Step 1.
        </p>
      </div>

      {/* Step 4: Restart */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Step 4: Restart Claude Desktop
        </h2>
        <p className="text-gray-600 mb-3">
          After saving the config file, restart Claude Desktop to load the MCP server.
        </p>
        <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
          <p className="text-sm text-blue-800">
            <strong>Tip:</strong> Start a new conversation and try saying{' '}
            <em>&quot;Please list my bookmarks&quot;</em> to verify the integration is working.
          </p>
        </div>
      </div>

      {/* Available Tools */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Available MCP Tools</h2>
        <p className="text-gray-600 mb-3">
          Once connected, Claude can use these tools to interact with your bookmarks:
        </p>
        <ul className="space-y-2 text-sm text-gray-600">
          <li className="flex items-start gap-2">
            <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-800">search_bookmarks</span>
            <span>Search your bookmarks by query, tags, or filters</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-800">get_bookmark</span>
            <span>Get details of a specific bookmark by ID</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-800">create_bookmark</span>
            <span>Create a new bookmark with URL, title, and tags</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-800">list_tags</span>
            <span>List all your bookmark tags</span>
          </li>
        </ul>
      </div>
    </div>
  )
}
