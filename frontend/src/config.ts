/**
 * Application configuration loaded from environment variables.
 */

export const config = {
  apiUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  mcpUrl: import.meta.env.VITE_MCP_URL || 'http://localhost:8001',
  auth0: {
    domain: import.meta.env.VITE_AUTH0_DOMAIN || '',
    clientId: import.meta.env.VITE_AUTH0_CLIENT_ID || '',
    audience: import.meta.env.VITE_AUTH0_AUDIENCE || '',
  },
  // Field length limits - shared with backend via env vars
  limits: {
    maxContentLength: parseInt(import.meta.env.VITE_MAX_CONTENT_LENGTH || '512000', 10),
    maxDescriptionLength: parseInt(import.meta.env.VITE_MAX_DESCRIPTION_LENGTH || '2000', 10),
    maxTitleLength: parseInt(import.meta.env.VITE_MAX_TITLE_LENGTH || '500', 10),
  },
} as const

/**
 * Dev mode can be enabled by:
 * 1. Setting VITE_DEV_MODE=true, OR
 * 2. Leaving VITE_AUTH0_DOMAIN empty
 *
 * When in dev mode, the app runs without authentication.
 * The backend must also have DEV_MODE=true for this to work.
 */
export const isDevMode = import.meta.env.VITE_DEV_MODE === 'true' || !config.auth0.domain
