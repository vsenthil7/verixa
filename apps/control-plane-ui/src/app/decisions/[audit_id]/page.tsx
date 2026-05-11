/**
 * Verixa Control Plane — Decision Detail (CP-15.4).
 *
 * Server Component. Renders the full ReplayResponse for a given
 * audit_id: request envelope, retrieved documents, tool I/O,
 * policy evaluations, and (when present) the triad review with
 * all three verdicts and commitments.
 *
 * Route: /decisions/[audit_id]
 *
 * Errors are caught and surfaced as in-page Cards; a 404 from the
 * API renders an "Audit not found" state with a back link instead
 * of throwing.
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
import { TOKENS, formatTimestampNs } from '@/components/design';
import { ApiError } from '@/lib/api-client';
import { getApiClient } from '@/lib/config';
import type { ReplayResponse } from '@/lib/api-client';

export const dynamic = 'force-dynamic';

interface DetailData {
  auditId: string;
  bundle: ReplayResponse | null;
  notFound: boolean;
  error: string | null;
}

async function loadDetail(auditId: string): Promise<DetailData> {
  const client = getApiClient();
  try {
    const bundle = await client.replay(auditId);
    return { auditId, bundle, notFound: false, error: null };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return { auditId, bundle: null, notFound: true, error: null };
    }
    return {
      auditId,
      bundle: null,
      notFound: false,
      error:
        e instanceof Error
          ? e.message
          : 'Failed to reach the Control Plane API.',
    };
  }
}

// Roughly classify a risk_score into a tier string for the RiskPill
// fallback when the ReplayResponse doesn't carry one explicitly
// (replay carries raw score; audit ledger has the classification).
function classifyRisk(score: number): string {
  if (score >= 0.8) return 'critical';
  if (score >= 0.5) return 'high';
  if (score >= 0.2) return 'medium';
  return 'low';
}

export default async function DecisionDetailPage({
  params,
}: {
  params: { audit_id: string };
}): Promise<JSX.Element> {
  const data = await loadDetail(params.audit_id);

  if (data.error !== null) {
    return (
      <PageShell title="Decision detail">
        <Card title="Connection error">
          <p style={{ color: TOKENS.color.decisionDeny }}>{data.error}</p>
        </Card>
        <BackLinks auditId={data.auditId} hasBundle={false} />
      </PageShell>
    );
  }

  if (data.notFound || data.bundle === null) {
    return (
      <PageShell title="Decision detail">
        <Card title="Audit not found">
          <p style={{ color: TOKENS.color.inkMuted }}>
            No replay bundle indexed for audit_id{' '}
            <MonoText>{data.auditId}</MonoText>. The audit may have
            been deleted or never written.
          </p>
        </Card>
        <BackLinks auditId={data.auditId} hasBundle={false} />
      </PageShell>
    );
  }

  const b = data.bundle;
  const riskTier = classifyRisk(b.risk_score);

  return (
    <PageShell
      title="Decision detail"
      subtitle="Full reconstructed decision context for this governed action."
    >
      <Card title="Summary">
        <KeyValueRow label="Audit ID">
          <MonoText>{b.audit_id}</MonoText>
        </KeyValueRow>
        <KeyValueRow label="Tenant ID">
          <MonoText truncate>{b.tenant_id}</MonoText>
        </KeyValueRow>
        <KeyValueRow label="Decision">
          <DecisionPill decision={b.decision} />
        </KeyValueRow>
        <KeyValueRow label="Risk">
          <RiskPill classification={riskTier} score={b.risk_score} />
        </KeyValueRow>
        <KeyValueRow label="Timestamp">
          {formatTimestampNs(b.timestamp_unix_ns)}
        </KeyValueRow>
      </Card>

      <Card title="Request envelope">
        <pre
          style={{
            background: TOKENS.color.inkBg,
            border: `1px solid ${TOKENS.color.inkBorder}`,
            borderRadius: TOKENS.radius.sm,
            padding: TOKENS.spacing.md,
            margin: 0,
            fontFamily: TOKENS.font.mono,
            fontSize: '0.8125rem',
            color: TOKENS.color.inkText,
            overflowX: 'auto',
            lineHeight: 1.5,
          }}
        >
          {JSON.stringify(b.request_envelope, null, 2)}
        </pre>
      </Card>

      <Card title={`Retrieved documents (${b.retrieved_documents.length})`}>
        {b.retrieved_documents.length === 0 ? (
          <EmptyState message="No documents retrieved for this decision." />
        ) : (
          <table style={tableStyle}>
            <thead>
              <tr style={{ color: TOKENS.color.inkMuted }}>
                <th style={th}>Document ID</th>
                <th style={th}>Content SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {b.retrieved_documents.map((d) => (
                <tr key={d.doc_id} style={rowStyle}>
                  <td style={td}>
                    <MonoText>{d.doc_id}</MonoText>
                  </td>
                  <td style={td}>
                    <MonoText truncate>{d.content_sha256}</MonoText>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title={`Tool I/O (${b.tool_io.length})`}>
        {b.tool_io.length === 0 ? (
          <EmptyState message="No tool calls recorded for this decision." />
        ) : (
          <pre
            style={{
              background: TOKENS.color.inkBg,
              border: `1px solid ${TOKENS.color.inkBorder}`,
              borderRadius: TOKENS.radius.sm,
              padding: TOKENS.spacing.md,
              margin: 0,
              fontFamily: TOKENS.font.mono,
              fontSize: '0.8125rem',
              color: TOKENS.color.inkText,
              overflowX: 'auto',
              lineHeight: 1.5,
            }}
          >
            {JSON.stringify(b.tool_io, null, 2)}
          </pre>
        )}
      </Card>

      <Card title={`Policy evaluations (${b.policy_evaluations.length})`}>
        {b.policy_evaluations.length === 0 ? (
          <EmptyState message="No policies evaluated for this decision." />
        ) : (
          <table style={tableStyle}>
            <thead>
              <tr style={{ color: TOKENS.color.inkMuted }}>
                <th style={th}>Package</th>
                <th style={th}>Decision</th>
                <th style={th}>Reason</th>
              </tr>
            </thead>
            <tbody>
              {b.policy_evaluations.map((p, i) => (
                <tr key={`${p.package}-${i}`} style={rowStyle}>
                  <td style={td}>
                    <MonoText>{p.package}</MonoText>
                  </td>
                  <td style={td}>
                    <span
                      style={{
                        color:
                          p.decision === 'pass'
                            ? TOKENS.color.decisionAllow
                            : TOKENS.color.decisionDeny,
                        fontWeight: 600,
                        fontSize: '0.875rem',
                      }}
                    >
                      {p.decision}
                    </span>
                  </td>
                  <td style={td}>{p.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {b.triad_review !== null && (
        <Card title="Triad review">
          <KeyValueRow label="Consensus kind">
            {b.triad_review.consensus_kind}
          </KeyValueRow>
          <KeyValueRow label="Agreed decision">
            {b.triad_review.agreed_decision ?? '— (split)'}
          </KeyValueRow>

          <h3
            style={{
              marginTop: TOKENS.spacing.lg,
              marginBottom: TOKENS.spacing.md,
              fontSize: '1rem',
              fontWeight: 600,
            }}
          >
            Verdicts
          </h3>
          <table style={tableStyle}>
            <thead>
              <tr style={{ color: TOKENS.color.inkMuted }}>
                <th style={th}>Reviewer</th>
                <th style={th}>Decision</th>
                <th style={th}>Confidence</th>
                <th style={th}>Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {b.triad_review.verdicts.map((v) => (
                <tr key={v.reviewer_id} style={rowStyle}>
                  <td style={td}>
                    <MonoText>{v.reviewer_id}</MonoText>
                  </td>
                  <td style={td}>
                    <DecisionPill decision={v.decision} />
                  </td>
                  <td style={td}>{(v.confidence * 100).toFixed(0)}%</td>
                  <td style={td}>{v.reasoning}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3
            style={{
              marginTop: TOKENS.spacing.lg,
              marginBottom: TOKENS.spacing.md,
              fontSize: '1rem',
              fontWeight: 600,
            }}
          >
            Commitments
          </h3>
          <p
            style={{
              color: TOKENS.color.inkMuted,
              fontSize: '0.8125rem',
              marginTop: 0,
              marginBottom: TOKENS.spacing.md,
            }}
          >
            Each reviewer commits to a SHA-256 of their verdict before
            seeing the others' — the protocol prevents post-hoc bias.
          </p>
          <table style={tableStyle}>
            <thead>
              <tr style={{ color: TOKENS.color.inkMuted }}>
                <th style={th}>Reviewer</th>
                <th style={th}>SHA-256 commitment</th>
              </tr>
            </thead>
            <tbody>
              {b.triad_review.commitments.map((c) => (
                <tr key={c.reviewer_id} style={rowStyle}>
                  <td style={td}>
                    <MonoText>{c.reviewer_id}</MonoText>
                  </td>
                  <td style={td}>
                    <MonoText truncate>{c.sha256_hex}</MonoText>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <BackLinks auditId={b.audit_id} hasBundle />
    </PageShell>
  );
}

function BackLinks({
  auditId,
  hasBundle,
}: {
  auditId: string;
  hasBundle: boolean;
}): JSX.Element {
  return (
    <div
      style={{
        display: 'flex',
        gap: TOKENS.spacing.lg,
        marginTop: TOKENS.spacing.md,
      }}
    >
      <Link
        href="/audit"
        style={{
          color: TOKENS.color.accent,
          textDecoration: 'none',
          fontSize: '0.875rem',
        }}
      >
        ← Back to audit log
      </Link>
      {hasBundle && (
        <Link
          href={`/dossier/new?audit_id=${auditId}`}
          style={{
            color: TOKENS.color.accent,
            textDecoration: 'none',
            fontSize: '0.875rem',
          }}
        >
          Generate signed dossier →
        </Link>
      )}
    </div>
  );
}

const tableStyle = {
  width: '100%',
  borderCollapse: 'collapse' as const,
  fontSize: '0.875rem',
};

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
  verticalAlign: 'top' as const,
};

const rowStyle = {
  borderTop: `1px solid ${TOKENS.color.inkBorder}`,
};
