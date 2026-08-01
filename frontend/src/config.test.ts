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
    expect(config.clerk).toBeDefined()
    expect(config.clerk).toHaveProperty('publishableKey')
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

  it('should be true when the Clerk publishable key is empty', async () => {
    // Preserved semantic from the previous provider: a missing provider key falls back
    // to dev mode rather than a broken login.
    ;(import.meta.env as Record<string, unknown>).VITE_CLERK_PUBLISHABLE_KEY = ''
    const { isDevMode } = await import('./config')
    expect(isDevMode).toBe(true)
  })

  it('should be false when the key is configured and VITE_DEV_MODE is not set', async () => {
    ;(import.meta.env as Record<string, unknown>).VITE_CLERK_PUBLISHABLE_KEY = 'pk_test_abc'
    const { isDevMode } = await import('./config')
    expect(isDevMode).toBe(false)
  })

  it('should be true when VITE_DEV_MODE is true even with the key configured', async () => {
    ;(import.meta.env as Record<string, unknown>).VITE_CLERK_PUBLISHABLE_KEY = 'pk_test_abc'
    ;(import.meta.env as Record<string, unknown>).VITE_DEV_MODE = 'true'
    const { isDevMode } = await import('./config')
    expect(isDevMode).toBe(true)
  })
})
