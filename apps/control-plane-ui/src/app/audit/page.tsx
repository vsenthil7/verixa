/**
 * Verixa Control Plane — Audit Log (CP-15.3).
 *
 * Server Component. Query params:
 *   - workflow_id (required): UUID of the workflow to filter by.
 *   - from (optional, ISO-8601): start of the time window.
 *                                Default: 30 days ago.
 *   - to   (optional, ISO-8601): end of the time window.
 *                                Default: now.
 *
 * Renders a full audit table for the matching window. If
 * workflow_id is missing, shows a list of workflows to pick from.
 */

import Link from 'next/link';

import {
  Card,
  DecisionPill,
  EmptyState,
  KeyValueRow,
  MonoText,
  PageShell,
  RiskPill,
} from '@/components/ui';
import { TOKENS, formatTimestamp } from '@/components/design';
import { getApiClient } from '@/lib/config';
import type { AuditEntry, WorkflowSummary } from '@/lib/api-client';

export const dynamic = 'force-dynamic';

interface SearchParams {
  workflow_id?: string;
  from?: string;
  to?: string;
}

interface AuditPageData {
  workflowId: string | null;
  from: string;
  to: string;
  entries: AuditEntry[];
  total: number;
  workflows: WorkflowSummary[]; // For the workflow-picker fallback.
  error: string | null;
}

async function loadAuditPage(params: SearchParams): Promise<AuditPageData> {
  const client = getApiClient();
  const now = new Date();
  const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  const from = params.from ?? monthAgo.toISOString();
  const to = params.to ?? now.toISOString();

  // No workflow_id -> fetch the workflow list so user can pick one.
  if (params.workflow_id === undefined || params.workflow_id === '') {
    try {
      const wf = await client.listWorkflows();
      return {
        workflowId: null,
        from,
        to,
        entries: [],
        total: 0,
        workflows: wf.workflows,
        error: null,
      };
    } catch (e) {
      return {
        workflowId: null,
        from,
        to,
        entries: [],
        total: 0,
        workflows: [],
        error:
          e instanceof Error
            ? e.message
            : 'Failed to reach the Control Plane API.',
      };
    }
  }

  try {
    const ar = await client.queryAudit({
      workflowId: params.workflow_id,
      from,
      to,
    });
    return {
      workflowId: params.workflow_id,
      from,
      to,
      entries: [...ar.entries].reverse(), // newest-first for display
      total: ar.total,
      workflows: [],
      error: null,
    };
  } catch (e) {
    return {
      workflowId: params.workflow_id,
      from,
      to,
      entries: [],
      total: 0,
      workflows: [],
      error:
        e instanceof Error
          ? e.message
          : 'Audit query failed.',
    };
  }
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const data = await loadAuditPage(searchParams);

  // ---- workflow-picker view ----
  if (data.workflowId === null) {
    return (
      <PageShell
        title="Audit Log"
        subtitle="Pick a workflow to inspect its decision history."
      >
        {data.error !== null ? (
          <Card title="Connection error">
            <p style={{ color: TOKENS.color.decisionDeny }}>{data.error}</p>
          </Card>
        ) : data.workflows.length === 0 ? (
          <Card>
            <EmptyState message="No workflows registered. Seed the demo or register one via POST /v1/control/workflows." />
          </Card>
        ) : (
          <Card title="Workflows">
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {data.workflows.map((w) => (
                <li
                  key={w.workflow_id}
                  style={{
                    padding: `${TOKENS.spacing.sm} 0`,
                    borderBottom: `1px solid ${TOKENS.color.inkBorder}`,
                  }}
                >
                  <Link
                    href={`/audit?workflow_id=${w.workflow_id}`}
                    style={{
                      color: TOKENS.color.accent,
                      textDecoration: 'none',
                      fontWeight: 500,
                    }}
                  >
                    {w.name}
                  </Link>
                  <div
                    style={{
                      fontSize: '0.875rem',
                      color: TOKENS.color.inkMuted,
                      marginTop: TOKENS.spacing.xs,
                    }}
                  >
                    {w.sector} · <MonoText truncate>{w.workflow_id}</MonoText>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </PageShell>
    );
  }

  // ---- filtered audit table view ----
  return (
    <PageShell
      title="Audit Log"
      subtitle={`Governed decisions for the selected workflow.`}
    >
      <Card title="Filter">
        <KeyValueRow label="Workflow ID">
          <MonoText truncate>{data.workflowId}</MonoText>
        </KeyValueRow>
        <KeyValueRow label="From">{formatTimestamp(data.from)}</KeyValueRow>
        <KeyValueRow label="To">{formatTimestamp(data.to)}</KeyValueRow>
        <KeyValueRow label="Matches">{data.total}</KeyValueRow>
      </Card>

      {data.error !== null ? (
        <Card title="Query error">
          <p style={{ color: TOKENS.color.decisionDeny }}>{data.error}</p>
        </Card>
      ) : data.entries.length === 0 ? (
        <Card>
          <EmptyState message="No governed decisions in this window." />
        </Card>
      ) : (
        <Card title={`Decisions (${data.total})`}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.875rem',
            }}
          >
            <thead>
              <tr style={{ color: TOKENS.color.inkMuted }}>
                <th style={th}>When</th>
                <th style={th}>Decision</th>
                <th style={th}>Risk</th>
                <th style={th}>Triad</th>
                <th style={th}>Audit ID</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((d) => (
                <tr
                  key={d.audit_id}
                  style={{
                    borderTop: `1px solid ${TOKENS.color.inkBorder}`,
                  }}
                >
                  <td style={td}>{formatTimestamp(d.timestamp)}</td>
                  <td style={td}>
                    <DecisionPill decision={d.decision} />
                  </td>
                  <td style={td}>
                    <RiskPill
                      classification={d.risk_classification}
                      score={d.risk_score}
                    />
                  </td>
                  <td style={td}>{d.triad_invoked ? 'yes' : 'no'}</td>
                  <td style={td}>
                    <MonoText truncate>{d.audit_id}</MonoText>
                  </td>
                  <td style={td}>
                    <Link
                      href={`/decisions/${d.audit_id}`}
                      style={{
                        color: TOKENS.color.accent,
                        textDecoration: 'none',
                        fontSize: '0.875rem',
                      }}
                    >
                      open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div style={{ marginTop: TOKENS.spacing.md }}>
        <Link
          href="/"
          style={{
            color: TOKENS.color.accent,
            textDecoration: 'none',
            fontSize: '0.875rem',
          }}
        >
          ← Back to dashboard
        </Link>
      </div>
    </PageShell>
  );
}

const th = {
  textAlign: 'left' as const,
  padding: `${TOKENS.spacing.sm} ${TOKENS.spacing.sm}`,
  fontWeight: 500,
  fontSize: '0.75rem',
  letterSpacing: '0.05em',
  textTransform: 'uppercase' as const,
};

const td = {
  padding: `${TOKENS.spacing.sm} ${TOKENS.spacing.sm}`,
  verticalAlign: 'middle' as const,
};
