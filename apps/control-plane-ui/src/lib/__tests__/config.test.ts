import { describe, expect, it, afterEach } from 'vitest';

import { getApiClient, getUiConfig } from '../config';

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  // Restore the env so tests don't leak into each other.
  for (const k of Object.keys(process.env)) {
    if (!(k in ORIGINAL_ENV)) {
      delete process.env[k];
    }
  }
  for (const [k, v] of Object.entries(ORIGINAL_ENV)) {
    process.env[k] = v;
  }
});

describe('getUiConfig', () => {
  it('uses VERIXA_CONTROL_PLANE_URL when set', () => {
    process.env.VERIXA_CONTROL_PLANE_URL = 'http://api.prod.example.com';
    expect(getUiConfig().controlPlaneBaseUrl).toBe(
      'http://api.prod.example.com',
    );
  });

  it('falls back to localhost when VERIXA_CONTROL_PLANE_URL is unset', () => {
    delete process.env.VERIXA_CONTROL_PLANE_URL;
    expect(getUiConfig().controlPlaneBaseUrl).toBe('http://localhost:8001');
  });
});

describe('getApiClient', () => {
  it('returns a configured ApiClient', () => {
    delete process.env.VERIXA_CONTROL_PLANE_URL;
    const client = getApiClient();
    expect(client).toBeDefined();
    expect(typeof client.listWorkflows).toBe('function');
  });
});
