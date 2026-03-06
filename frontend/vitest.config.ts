import path from 'node:path'

import { defineConfig } from 'vitest/config'

export default defineConfig({
  root: path.resolve(__dirname),
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./test/setup.ts'],
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['**/node_modules/**', '**/.next/**'],
    css: true,
  },
})
