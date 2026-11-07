import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    setupFiles: ['./tests/setup.ts'],
    globalSetup: ['./tests/global-setup.ts'],
    include: ['tests/**/*.test.ts'],
    // All test files share one SQLite file; run them serially to avoid write races.
    fileParallelism: false,
    testTimeout: 30_000,
    hookTimeout: 30_000,
  },
});
