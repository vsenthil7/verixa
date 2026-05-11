/**
 * Verixa UI runtime config (CP-15.2).
 *
 * Centralises environment-driven values so pages don't reach into
 * `process.env` directly. Single source of truth for the Control
 * Plane API base URL.
 */

import { createApiClient, type ApiClient } from './api-client';

export interface UiConfig {
  controlPlaneBaseUrl: string;
}

export function getUiConfig(): UiConfig {
  return {
    controlPlaneBaseUrl:
      process.env.VERIXA_CONTROL_PLANE_URL ?? 'http://localhost:8001',
  };
}

/**
 * Convenience factory for pages that just need a configured client.
 * Pages call this in their Server Component body.
 */
export function getApiClient(): ApiClient {
  return createApiClient({ baseUrl: getUiConfig().controlPlaneBaseUrl });
}
