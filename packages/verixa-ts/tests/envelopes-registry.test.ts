/**
 * CP-66 vitest suite for verixa-ts envelopes (registry: agent + tool).
 *
 * Mirrors the Python CP-62 test file (tests for AgentRegisterResponse +
 * ToolRegisterResponse). Coverage target: keep envelopes.ts at 100%
 * after the CP-66 append.
 *
 * Tests cover:
 *   - Positive parses (Agent + Tool with empty/populated allowed list)
 *   - Missing required fields (parametrised per envelope)
 *   - Invalid UUID at top level + invalid UUID inside list with index prefix
 *   - Bool/string strict-typing rejection
 *   - Forward-compat: extra fields ignored
 *   - Immutability: allowedWorkflowIds frozen array
 */

import { describe, expect, it, test } from 'vitest';

import {
  type AgentRegisterResponse,
  type ToolRegisterResponse,
  InvalidEnvelopeError,
  parseAgentRegisterResponse,
  parseToolRegisterResponse,
} from '../src/envelopes.js';

const now = (): string => new Date().toISOString();

function agentRegisterPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    agent_id: '00000000-0000-0000-0000-000000000010',
    workflow_id: '00000000-0000-0000-0000-000000000011',
    spiffe_id: 'spiffe://verixa.local/prod/runtime-gateway/pod-1',
    role: 'gateway',
    created_at: now(),
    ...overrides,
  };
}

function toolRegisterPayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    tool_id: '00000000-0000-0000-0000-000000000020',
    name: 'firewall-checker',
    is_active: true,
    allowed_workflow_ids: [],
    created_at: now(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// parseAgentRegisterResponse
// ---------------------------------------------------------------------------

describe('parseAgentRegisterResponse()', () => {
  it('parses a minimal payload', () => {
    const parsed = parseAgentRegisterResponse(agentRegisterPayload());
    expect(parsed.role).toBe('gateway');
    expect(parsed.spiffeId.startsWith('spiffe://verixa.local/')).toBe(true);
    expect(parsed.agentId).toBe('00000000-0000-0000-0000-000000000010');
    expect(parsed.workflowId).toBe('00000000-0000-0000-0000-000000000011');
    expect(parsed.createdAt).toBeInstanceOf(Date);
  });

  it('ignores extra fields (forward-compat)', () => {
    const parsed = parseAgentRegisterResponse(
      agentRegisterPayload({ future_field: 42 }),
    );
    expect(parsed.role).toBe('gateway');
  });

  it('rejects non-record input', () => {
    expect(() => parseAgentRegisterResponse([1, 2, 3])).toThrow(
      InvalidEnvelopeError,
    );
  });

  test.each(['agent_id', 'workflow_id', 'spiffe_id', 'role', 'created_at'])(
    'rejects missing required field %s',
    (missing) => {
      const payload = agentRegisterPayload();
      delete payload[missing];
      expect(() => parseAgentRegisterResponse(payload)).toThrow(
        new RegExp(`field ${missing}`),
      );
    },
  );

  it('rejects non-string spiffe_id', () => {
    const payload = agentRegisterPayload({ spiffe_id: 42 });
    expect(() => parseAgentRegisterResponse(payload)).toThrow(
      /field spiffe_id/,
    );
  });

  it('rejects invalid UUID for agent_id', () => {
    const payload = agentRegisterPayload({ agent_id: 'not-a-uuid' });
    expect(() => parseAgentRegisterResponse(payload)).toThrow(
      /not a valid UUID/,
    );
  });
});

// ---------------------------------------------------------------------------
// parseToolRegisterResponse
// ---------------------------------------------------------------------------

describe('parseToolRegisterResponse()', () => {
  it('parses with empty allowed_workflow_ids (any-workflow)', () => {
    const parsed = parseToolRegisterResponse(toolRegisterPayload());
    expect(parsed.name).toBe('firewall-checker');
    expect(parsed.isActive).toBe(true);
    expect(parsed.allowedWorkflowIds).toEqual([]);
  });

  it('parses with populated allowed_workflow_ids (restricted)', () => {
    const wf1 = '00000000-0000-0000-0000-000000000021';
    const wf2 = '00000000-0000-0000-0000-000000000022';
    const parsed = parseToolRegisterResponse(
      toolRegisterPayload({ allowed_workflow_ids: [wf1, wf2] }),
    );
    expect(parsed.allowedWorkflowIds.length).toBe(2);
    expect(parsed.allowedWorkflowIds[0]).toBe(wf1);
    expect(parsed.allowedWorkflowIds[1]).toBe(wf2);
  });

  it('returns a frozen allowed_workflow_ids array', () => {
    const parsed = parseToolRegisterResponse(toolRegisterPayload());
    expect(Object.isFrozen(parsed.allowedWorkflowIds)).toBe(true);
  });

  it('rejects non-array allowed_workflow_ids', () => {
    const payload = toolRegisterPayload({ allowed_workflow_ids: 'oops' });
    expect(() => parseToolRegisterResponse(payload)).toThrow(
      /expected array of uuids/,
    );
  });

  it('rejects invalid UUID inside list with index prefix', () => {
    const payload = toolRegisterPayload({
      allowed_workflow_ids: [
        '00000000-0000-0000-0000-000000000023',
        'not-a-uuid',
      ],
    });
    expect(() => parseToolRegisterResponse(payload)).toThrow(
      /allowed_workflow_ids\[1\]/,
    );
  });

  it('rejects non-string element inside list with index prefix', () => {
    const payload = toolRegisterPayload({
      allowed_workflow_ids: ['00000000-0000-0000-0000-000000000024', 42],
    });
    expect(() => parseToolRegisterResponse(payload)).toThrow(
      /allowed_workflow_ids\[1\]: expected uuid string/,
    );
  });

  it('rejects int for is_active (boolean strict)', () => {
    const payload = toolRegisterPayload({ is_active: 1 });
    expect(() => parseToolRegisterResponse(payload)).toThrow(
      /field is_active: expected bool/,
    );
  });

  it('accepts is_active=false', () => {
    const parsed = parseToolRegisterResponse(
      toolRegisterPayload({ is_active: false }),
    );
    expect(parsed.isActive).toBe(false);
  });

  it('rejects non-record input', () => {
    expect(() => parseToolRegisterResponse(42)).toThrow(InvalidEnvelopeError);
  });

  test.each([
    'tool_id',
    'name',
    'is_active',
    'allowed_workflow_ids',
    'created_at',
  ])('rejects missing required field %s', (missing) => {
    const payload = toolRegisterPayload();
    delete payload[missing];
    expect(() => parseToolRegisterResponse(payload)).toThrow(
      new RegExp(`field ${missing}`),
    );
  });
});

// ---------------------------------------------------------------------------
// Type-only sanity
// ---------------------------------------------------------------------------

describe('TypeScript type surface for CP-66', () => {
  it('AgentRegisterResponse interface has expected field types', () => {
    const agent: AgentRegisterResponse = parseAgentRegisterResponse(
      agentRegisterPayload(),
    );
    expect(typeof agent.agentId).toBe('string');
    expect(typeof agent.spiffeId).toBe('string');
    expect(agent.createdAt).toBeInstanceOf(Date);
  });

  it('ToolRegisterResponse interface has expected field types', () => {
    const tool: ToolRegisterResponse = parseToolRegisterResponse(
      toolRegisterPayload(),
    );
    expect(typeof tool.isActive).toBe('boolean');
    expect(Array.isArray(tool.allowedWorkflowIds)).toBe(true);
  });
});
