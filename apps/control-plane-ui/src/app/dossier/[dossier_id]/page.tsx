/**
 * Verixa Control Plane — Dossier Viewer (CP-15.5).
 *
 * Server Component. Route: /dossier/[dossier_id]
 *
 * Renders a SignedDossier as a four-section auditor-facing
 * evidence pack:
 *   1. Cover         (audit_id, tenant_id, decision, risk, generated_at)
 *   2. Decision trail (policy evaluations, triad consensus + dissenters)
 *   3. Evidence      (retrieved documents with SHA-256 fingerprints)
 *   4. Crypto proof  (replay_storage_key, signing_key_id,
 *                     128-char signature, 64-char public key)
 *
 * The signature_hex and public_key_hex are displayed verbatim in
 * mono so the auditor can copy-paste them into an offline
 * verifier. A "Download as JSON" link bundles the full response
 * into a downloadable data URI -- the auditor takes that JSON,
 * runs `tools/audit_verify.py` or the equivalent, and confirms
 * the signature offline without trusting Verixa.
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
import type { DossierGetResponse } from '@/lib/api-client';

export const dynamic = 'force-dynamic';

interface DossierPageData {
  dossierId: string;
  dossier: DossierGetResponse | null;
  notFound: boolean;
  error: string | null;
}

async function loadDossier(dossierId: string): Promise<DossierPageData> {
  const client = getApiClient();
  try {
    const dossier = await client.getDossier(dossierId);
    return { dossierId, dossier, notFound: false, error: null };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return { dossierId, dossier: null, notFound: true, error: null };
    }
    return {
      dossierId,
      dossier: null,
      notFound: false,
      error:
        e instanceof Error
          ? e.message
          : 'Failed to reach the Control Plane API.',
    };
  }
}

export default async function DossierViewerPage({
  params,
}: {
  params: { dossier_id: string };
}): Promise<JSX.Element> {
  const data = await loadDossier(params.dossier_id);

  if (data.error !== null) {
    return (
      <PageShell title="Signed dossier">
        <Card title="Connection error">
          <p style={{ color: TOKENS.color.decisionDeny }}>{data.error}</p>
        </Card>
        <FooterLinks dossierId={data.dossierId} />
      </PageShell>
    );
  }

  if (data.notFound || data.dossier === null) {
    return (
      <PageShell title="Signed dossier">
        <Card title="Dossier not found">
          <p style={{ color: TOKENS.color.inkMuted }}>
            No dossier at dossier_id{' '}
            <MonoText>{data.dossierId}</MonoText>. The dossier may
            never have been generated.
          </p>
        </Card>
        <FooterLinks dossierId={data.dossierId} />
      </PageShell>
    );
  }

  const d = data.dossier;
  const m = d.manifest;

  // Build the data URI for offline download. JSON.stringify with
  // two-space indent keeps it human-readable for auditors who
  // inspect by hand.
  const downloadJson = JSON.stringify(d, null, 2);
  const downloadDataUri = `data:application/json;charset=utf-8,${encodeURIComponent(downloadJson)}`;
  const downloadFilename = `verixa-dossier-${d.dossier_id}.json`;

  return (
    <PageShell
      title="Signed dossier"
      subtitle="Auditor-facing evidence pack. The signature can be verified offline."
    >
      {/* ---- 1. Cover ---- */}
      <Card title="Cover">
        <KeyValueRow label="Dossier ID">
          <MonoText>{d.dossier_id}</MonoText>
        </KeyValueRow>
        <KeyValueRow label="Audit ID">
          <MonoText>{d.audit_id}</MonoText>
        </KeyValueRow>
        <KeyValueRow label="Tenant ID">
          <MonoText truncate>{m.tenant_id}</MonoText>
        </KeyValueRow>
        <KeyValueRow label="Decision">
          <DecisionPill decision={m.decision} />
        </KeyValueRow>
        <KeyValueRow label="Risk">
          <RiskPill
            classification={m.risk_classification}
            score={m.risk_score}
          />
        </KeyValueRow>
        <KeyValueRow label="Action summary">
          {m.action_summary || (
            <span style={{ color: TOKENS.color.inkMuted, fontStyle: 'italic' }}>
              (none supplied)
            </span>
          )}
        </KeyValueRow>
        <KeyValueRow label="Generated">
          {formatTimestampNs(m.generated_at_unix_ns)}
        </KeyValueRow>
        <KeyValueRow label="Schema version">{m.schema_version}</KeyValueRow>
      </Card>

      {/* ---- 2. Decision trail ---- */}
      <Card title="Decision trail">
        <h3 style={subheadStyle}>Policy evaluations</h3>
        {m.policy_evaluations.length === 0 ? (
          <EmptyState message="No policies evaluated." />
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
              {m.policy_evaluations.map((p, i) => (
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

        <h3 style={subheadStyle}>Triad consensus</h3>
        {m.triad_consensus === null ? (
          <EmptyState message="No triad review was invoked for this decision." />
        ) : (
          <>
            <KeyValueRow label="Consensus kind">
              {m.triad_consensus}
            </KeyValueRow>
            <KeyValueRow label="Agreed decision">
              {m.triad_agreed_decision ?? '— (split)'}
            </KeyValueRow>
            <KeyValueRow label="Dissenters">
              {m.triad_dissenters.length === 0 ? (
                <span style={{ color: TOKENS.color.inkMuted }}>none</span>
              ) : (
                m.triad_dissenters.map((rid, i) => (
                  <span key={rid}>
                    {i > 0 && ', '}
                    <MonoText>{rid}</MonoText>
                  </span>
                ))
              )}
            </KeyValueRow>
          </>
        )}
      </Card>

      {/* ---- 3. Evidence ---- */}
      <Card title="Evidence">
        <h3 style={subheadStyle}>
          Retrieved documents ({m.retrieved_documents.length})
        </h3>
        {m.retrieved_documents.length === 0 ? (
          <EmptyState message="No documents were retrieved for this decision." />
        ) : (
          <table style={tableStyle}>
            <thead>
              <tr style={{ color: TOKENS.color.inkMuted }}>
                <th style={th}>Document ID</th>
                <th style={th}>Content SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {m.retrieved_documents.map((doc) => (
                <tr key={doc.doc_id} style={rowStyle}>
                  <td style={td}>
                    <MonoText>{doc.doc_id}</MonoText>
                  </td>
                  <td style={td}>
                    <MonoText>{doc.content_sha256}</MonoText>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* ---- 4. Crypto proof ---- */}
      <Card title="Crypto proof">
        <p
          style={{
            color: TOKENS.color.inkMuted,
            fontSize: '0.875rem',
            marginTop: 0,
            marginBottom: TOKENS.spacing.md,
          }}
        >
          The signature is Ed25519 over the canonical-JSON encoding of
          the manifest above. An auditor can verify it offline without
          trusting Verixa — pass the JSON, the signature, and the
          public key to any standard Ed25519 verifier.
        </p>

        <KeyValueRow label="Signing key ID">
          {m.signing_key_id}
        </KeyValueRow>
        <KeyValueRow label="Replay storage key">
          <MonoText truncate>{m.replay_storage_key}</MonoText>
        </KeyValueRow>

        <h3 style={subheadStyle}>Signature (Ed25519, 128 hex chars)</h3>
        <MonoBlock>{d.signature_hex}</MonoBlock>

        <h3 style={subheadStyle}>Public key (Ed25519, 64 hex chars)</h3>
        <MonoBlock>{d.public_key_hex}</MonoBlock>

        <div style={{ marginTop: TOKENS.spacing.lg }}>
          <a
            href={downloadDataUri}
            download={downloadFilename}
            style={{
              display: 'inline-block',
              padding: `${TOKENS.spacing.sm} ${TOKENS.spacing.md}`,
              background: TOKENS.color.accent,
              color: TOKENS.color.inkBg,
              textDecoration: 'none',
              borderRadius: TOKENS.radius.sm,
              fontWeight: 600,
              fontSize: '0.875rem',
            }}
          >
            Download dossier as JSON
          </a>
        </div>
      </Card>

      <FooterLinks dossierId={d.dossier_id} auditId={d.audit_id} />
    </PageShell>
  );
}

function MonoBlock({ children }: { children: string }): JSX.Element {
  return (
    <pre
      style={{
        background: TOKENS.color.inkBg,
        border: `1px solid ${TOKENS.color.inkBorder}`,
        borderRadius: TOKENS.radius.sm,
        padding: TOKENS.spacing.md,
        margin: 0,
        marginBottom: TOKENS.spacing.md,
        fontFamily: TOKENS.font.mono,
        fontSize: '0.8125rem',
        color: TOKENS.color.inkText,
        wordBreak: 'break-all',
        whiteSpace: 'pre-wrap',
        lineHeight: 1.4,
      }}
    >
      {children}
    </pre>
  );
}

function FooterLinks({
  dossierId,
  auditId,
}: {
  dossierId: string;
  auditId?: string;
}): JSX.Element {
  // dossierId is intentionally unused in markup -- it's reserved
  // for a "Copy share link" client component in a follow-up CP.
  void dossierId;
  return (
    <div
      style={{
        display: 'flex',
        gap: TOKENS.spacing.lg,
        marginTop: TOKENS.spacing.md,
      }}
    >
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
      {auditId !== undefined && (
        <Link
          href={`/decisions/${auditId}`}
          style={{
            color: TOKENS.color.accent,
            textDecoration: 'none',
            fontSize: '0.875rem',
          }}
        >
          View decision detail →
        </Link>
      )}
    </div>
  );
}

const subheadStyle = {
  marginTop: TOKENS.spacing.lg,
  marginBottom: TOKENS.spacing.md,
  fontSize: '1rem',
  fontWeight: 600,
};

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
