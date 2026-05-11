/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: false,
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      // - index.ts: pure re-export barrel; covered by leaf modules
      // - _backup/**: pre-edit snapshots kept for safety per session
      //   rules; not part of the published package + must not affect
      //   the 100% coverage gate.
      exclude: ['src/index.ts', 'src/_backup/**'],
      reporter: ['text', 'html', 'json-summary'],
      thresholds: {
        lines: 100,
        functions: 100,
        branches: 100,
        statements: 100,
      },
    },
  },
});
