/**
 * Playwright E2E test configuration (CP-21).
 *
 * Boots two long-running servers before the test run:
 *   1. The FastAPI Control Plane (port 8001) via the production
 *      ASGI entry-point at verixa_control_plane.asgi:app. Import-time
 *      seed runs once; every endpoint serves the demo data.
 *   2. The Next.js dev server (port 3000) pointed at the FastAPI
 *      via VERIXA_CONTROL_PLANE_URL.
 *
 * The webServer entries use ``reuseExistingServer`` in non-CI mode
 * so local re-runs are fast (no spin-up cost when both servers are
 * already running).
 *
 * Tests live in ./tests-e2e/*.spec.ts. They're separate from vitest
 * unit tests (./src/**\/__tests__/*.test.ts) so the two runners
 * don't fight over the same glob.
 *
 * Cross-platform uvicorn invocation:
 *   The same config runs on a Windows dev box AND on Linux CI
 *   runners. process.platform branches between
 *   ``.venv\Scripts\python`` (Windows venv layout) and
 *   ``.venv/bin/python`` (Linux/macOS venv layout).
 *   VERIXA_UVICORN_CMD env override wins over both -- used by
 *   GitHub Actions to point at the runner's installed Poetry venv
 *   path explicitly (CP-21.2).
 */

import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const FRONTEND_PORT = 3000;
const BACKEND_PORT = 8001;

/**
 * Build the uvicorn command for the FastAPI Control Plane.
 *
 * Precedence:
 *   1. VERIXA_UVICORN_CMD env var (CI sets this explicitly).
 *   2. process.platform === 'win32' -> .venv\Scripts\python -m uvicorn
 *   3. anything else                -> .venv/bin/python -m uvicorn
 */
function buildUvicornCommand(): string {
  const override = process.env.VERIXA_UVICORN_CMD;
  if (override !== undefined && override.length > 0) {
    return (
      `${override} verixa_control_plane.asgi:app ` +
      `--host 127.0.0.1 --port ${BACKEND_PORT} --workers 1`
    );
  }
  const isWindows = process.platform === 'win32';
  const pythonPath = isWindows
    ? path.join('.venv', 'Scripts', 'python')
    : path.join('.venv', 'bin', 'python');
  return (
    `${pythonPath} -m uvicorn verixa_control_plane.asgi:app ` +
    `--host 127.0.0.1 --port ${BACKEND_PORT} --workers 1`
  );
}

// Absolute path to the monorepo root (two parents up from
// apps/control-plane-ui/). The FastAPI webServer must boot from
// there so the .venv and the verixa_control_plane import path
// resolve consistently across platforms.
const REPO_ROOT = path.resolve(__dirname, '..', '..');

export default defineConfig({
  testDir: './tests-e2e',
  // The dev server's first request is slow (Next.js compiles on
  // demand), so be generous with the per-test timeout.
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  // Don't parallelise: the two servers are stateful + shared.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Both servers boot before the first test runs. ``url`` is
  // probed until 2xx/3xx; once both report up, tests start.
  webServer: [
    {
      // FastAPI control plane with seeded demo data.
      // ``cwd`` is honoured by Playwright -- we point it at the
      // monorepo root so the relative .venv path resolves and the
      // verixa_control_plane Python package is importable.
      command: buildUvicornCommand(),
      cwd: REPO_ROOT,
      url: `http://127.0.0.1:${BACKEND_PORT}/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // Next.js dev server pointed at the FastAPI.
      command: 'pnpm dev',
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        VERIXA_CONTROL_PLANE_URL: `http://127.0.0.1:${BACKEND_PORT}`,
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
});
