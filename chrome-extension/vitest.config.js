import { defineConfig } from 'vitest/config';

export default defineConfig({
  // Mirrors build.mjs's esbuild define so tests exercise the source modules
  // directly (the plan's test-target decision: source with mocks; the built
  // artifact is covered by test/build.test.js and the manual unpacked pass).
  define: {
    __TIDDLY_API_URL__: JSON.stringify('https://api.tiddly.me'),
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './test/setup.js',
  },
});
