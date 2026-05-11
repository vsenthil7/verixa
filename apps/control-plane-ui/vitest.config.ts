import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'happy-dom',
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/__tests__/**',
        'src/**/*.test.{ts,tsx}',
        'src/app/layout.tsx',
        'src/app/page.tsx',
        // Pages added in CP-15.2+ are server components calling the
        // API client; their logic is covered via the api-client tests
        // and via Python integration tests. The JSX presentation
        // doesn't earn unit-test cost on a hackathon timeline.
        'src/app/**/page.tsx',
        // Presentational primitives -- pure JSX rendering, would
        // require React Testing Library setup to test meaningfully.
        // Logic lives in design.ts which IS 100pct covered.
        'src/components/ui.tsx',
      ],
      thresholds: {
        lines: 100,
        functions: 100,
        branches: 100,
        statements: 100,
      },
    },
  },
});
