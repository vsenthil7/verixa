/**
 * Verixa Control Plane — Dashboard (CP-15.2).
 *
 * Server Component. Fetches the workflow list and recent audit
 * entries from the Control Plane FastAPI service. Renders a clean
 * dark-themed overview: every workflow card + the most recent
 * governed decisions per workflow.
 *
 * Pages-as-data: no client-side state, no auth, no forms. Refresh
 * the page to pick up new decisions.
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

interface DashboardData {
  workflows: WorkflowSummary[];
  recentDecisionsByWorkflow: Map<string, AuditEntry[]>;
  error: string | null;
}

async function loadDashboard(): Promise<DashboardData> {
  const client = getApiClient();
  try {
    const wf = await client.listWorkflows();
    const decisions = new Map<string, AuditEntry[]>();
    // Query a wide window (Phase-0: last 30 days). Production would
    // honour a real range from the URL.
    const now = new Date();
    const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    for (const w of wf.workflows) {
      try {
        const ar = await client.queryAudit({
          workflowId: w.workflow_id,
          from: monthAgo.toISOString(),
          to: now.toISOString(),
        });
        decisions.set(w.workflow_id, ar.entries.slice(-5).reverse());
      } catch {
        decisions.set(w.workflow_id, []);
      }
    }
    return {
      workflows: wf.workflows,
      recentDecisionsByWorkflow: decisions,
      error: null,
    };
  } catch (e) {
    return {
      workflows: [],
      recentDecisionsByWorkflow: new Map(),
      error:
        e instanceof Error
          ? e.message
          : 'Failed to reach the Control Plane API.',
    };
  }
}

export default async function HomePage(): Promise<JSX.Element> {
  const data = await loadDashboard();

  return (
    <PageShell
      title="Dashboard"
      subtitle="Workflows under Verixa governance, with recent decisions."
    >
      {data.error !== null ? (
        <Card title="Connection error">
          <p style={{ color: TOKENS.color.decisionDeny }}>{data.error}</p>
          <p
            style={{ color: TOKENS.color.inkMuted, marginTop: TOKENS.spacing.md }}
          >
            Confirm the Control Plane API is running and{' '}
            <code>VERIXA_CONTROL_PLANE_URL</code> points at it.
          </p>
        </Card>
      ) : data.workflows.length === 0 ? (
        <Card>
          <EmptyState message="No workflows registered yet. Run seed_financial_services_demo or register via POST /v1/control/workflows." />
        </Card>
      ) : (
        data.workflows.map((w) => {
          const decisions =
            data.recentDecisionsByWorkflow.get(w.workflow_id) ?? [];
          return (
            <Card key={w.workflow_id} title={w.name}>
              <KeyValueRow label="Workflow ID">
                <MonoText truncate>{w.workflow_id}</MonoText>
              </KeyValueRow>
              <KeyValueRow label="Sector">{w.sector}</KeyValueRow>
              <KeyValueRow label="Risk escalation threshold">
                {`${(w.risk_threshold_escalate * 100).toFixed(0)}%`}
              </KeyValueRow>
              <KeyValueRow label="Registered agents">
                {w.agent_count}
              </KeyValueRow>
              <KeyValueRow label="Created">
                {formatTimestamp(w.created_at)}
              </KeyValueRow>

              <h3
                style={{
                  marginTop: TOKENS.spacing.lg,
                  marginBottom: TOKENS.spacing.md,
                  fontSize: '1rem',
                  fontWeight: 600,
                }}
              >
                Recent decisions
              </h3>
              {decisions.length === 0 ? (
                <EmptyState message="No decisions in the last 30 days." />
              ) : (
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
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((d) => (
                      <tr key={d.audit_id} style={{ borderTop: `1px solid ${TOKENS.color.inkBorder}` }}>
                        <td style={td}>{formatTimestamp(d.timestamp)}</td>
                        <td style={td}><DecisionPill decision={d.decision} /></td>
                        <td style={td}>
                          <RiskPill
                            classification={d.risk_classification}
                            score={d.risk_score}
                          />
                        </td>
                        <td style={td}>{d.triad_invoked ? 'yes' : 'no'}</td>
                        <td style={td}>
                          <Link
                            href={`/decisions/${d.audit_id}`}
                            style={{
                              color: TOKENS.color.accent,
                              textDecoration: 'none',
                            }}
                          >
                            <MonoText truncate>{d.audit_id}</MonoText>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div
                style={{ marginTop: TOKENS.spacing.md }}
              >
                <Link
                  href={`/audit?workflow_id=${w.workflow_id}`}
                  style={{
                    color: TOKENS.color.accent,
                    textDecoration: 'none',
                    fontSize: '0.875rem',
                  }}
                >
                  View full audit log →
                </Link>
              </div>
            </Card>
          );
        })
      )}
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
