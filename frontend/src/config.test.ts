import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('config', () => {
  // Store original env values
  const originalEnv = { ...import.meta.env }

  afterEach(() => {
    // Restore original env values
    Object.assign(import.meta.env, originalEnv)
  })

  it('should export config object with expected structure', async () => {
    const { config } = await import('./config')
    expect(config).toBeDefined()
    expect(config.apiUrl).toBeDefined()
    expect(typeof config.apiUrl).toBe('string')
    expect(config.auth0).toBeDefined()
    expect(config.auth0).toHaveProperty('domain')
    expect(config.auth0).toHaveProperty('clientId')
    expect(config.auth0).toHaveProperty('audience')
  })

  it('should default apiUrl to localhost:8000', async () => {
    // Clear the env var
    delete (import.meta.env as Record<string, unknown>).VITE_API_URL
    // Re-import to get fresh config
    vi.resetModules()
    const { config } = await import('./config')
    expect(config.apiUrl).toBe('http://localhost:8000')
  })
})

describe('isDevMode', () => {
  beforeEach(() => {
    vi.resetModules()
    // Reset dev mode flag
    delete (import.meta.env as Record<string, unknown>).VITE_DEV_MODE
  })

  it('should be true when auth0 domain is empty', async () => {
    ;(import.meta.env as Record<string, unknown>).VITE_AUTH0_DOMAIN = ''
    const { isDevMode } = await import('./config')
    expect(isDevMode).toBe(true)
  })

  it('should be false when auth0 domain is configured and VITE_DEV_MODE is not set', async () => {
    ;(import.meta.env as Record<string, unknown>).VITE_AUTH0_DOMAIN = 'test.auth0.com'
    const { isDevMode } = await import('./config')
    expect(isDevMode).toBe(false)
  })

  it('should be true when VITE_DEV_MODE is true even with auth0 domain configured', async () => {
    ;(import.meta.env as Record<string, unknown>).VITE_AUTH0_DOMAIN = 'test.auth0.com'
    ;(import.meta.env as Record<string, unknown>).VITE_DEV_MODE = 'true'
    const { isDevMode } = await import('./config')
    expect(isDevMode).toBe(true)
  })
})
