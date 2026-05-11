/**
 * Verixa UI presentational primitives (CP-15.2).
 *
 * Functional components using inline styles backed by the design
 * tokens in design.ts. No client hooks — these render fine inside
 * Server Components.
 */

import type { CSSProperties, ReactNode } from 'react';

import {
  TOKENS,
  decisionColor,
  riskColor,
  shortUuid,
} from './design';

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function PageShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <main
      style={{
        minHeight: '100vh',
        background: TOKENS.color.inkBg,
        color: TOKENS.color.inkText,
        fontFamily: TOKENS.font.body,
        padding: `${TOKENS.spacing.xl} ${TOKENS.spacing.xl}`,
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
        <header style={{ marginBottom: TOKENS.spacing.xl }}>
          <div
            style={{
              fontSize: '0.875rem',
              color: TOKENS.color.accent,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: TOKENS.spacing.xs,
            }}
          >
            Verixa Control Plane
          </div>
          <h1
            style={{
              fontSize: '2rem',
              margin: 0,
              fontWeight: 600,
              letterSpacing: '-0.01em',
            }}
          >
            {title}
          </h1>
          {subtitle !== undefined && (
            <p
              style={{
                color: TOKENS.color.inkMuted,
                marginTop: TOKENS.spacing.sm,
                marginBottom: 0,
                fontSize: '1rem',
              }}
            >
              {subtitle}
            </p>
          )}
        </header>
        {children}
      </div>
    </main>
  );
}

export function Card({
  title,
  children,
  style,
}: {
  title?: string;
  children: ReactNode;
  style?: CSSProperties;
}): JSX.Element {
  return (
    <section
      style={{
        background: TOKENS.color.inkSurface,
        border: `1px solid ${TOKENS.color.inkBorder}`,
        borderRadius: TOKENS.radius.md,
        padding: TOKENS.spacing.lg,
        marginBottom: TOKENS.spacing.lg,
        ...style,
      }}
    >
      {title !== undefined && (
        <h2
          style={{
            fontSize: '1.125rem',
            margin: 0,
            marginBottom: TOKENS.spacing.md,
            fontWeight: 600,
            color: TOKENS.color.inkText,
          }}
        >
          {title}
        </h2>
      )}
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Pills + badges
// ---------------------------------------------------------------------------

export function DecisionPill({ decision }: { decision: string }): JSX.Element {
  const c = decisionColor(decision);
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.125rem 0.5rem',
        borderRadius: TOKENS.radius.sm,
        background: `${c}22`,
        color: c,
        fontSize: '0.75rem',
        fontWeight: 600,
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
        border: `1px solid ${c}55`,
      }}
    >
      {decision}
    </span>
  );
}

export function RiskPill({
  classification,
  score,
}: {
  classification: string;
  score?: number;
}): JSX.Element {
  const c = riskColor(classification);
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.125rem 0.5rem',
        borderRadius: TOKENS.radius.sm,
        background: `${c}22`,
        color: c,
        fontSize: '0.75rem',
        fontWeight: 600,
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
        border: `1px solid ${c}55`,
      }}
    >
      {classification}
      {score !== undefined && (
        <span style={{ opacity: 0.75, marginLeft: TOKENS.spacing.xs }}>
          {`(${(score * 100).toFixed(0)}%)`}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Key-value rows + mono code
// ---------------------------------------------------------------------------

export function KeyValueRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '180px 1fr',
        gap: TOKENS.spacing.md,
        padding: `${TOKENS.spacing.sm} 0`,
        borderBottom: `1px solid ${TOKENS.color.inkBorder}`,
        alignItems: 'baseline',
      }}
    >
      <div
        style={{
          color: TOKENS.color.inkMuted,
          fontSize: '0.875rem',
        }}
      >
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}

export function MonoText({
  children,
  truncate,
}: {
  children: string;
  truncate?: boolean;
}): JSX.Element {
  const text = truncate === true ? shortUuid(children) : children;
  return (
    <code
      style={{
        fontFamily: TOKENS.font.mono,
        fontSize: '0.875rem',
        color: TOKENS.color.inkText,
        wordBreak: 'break-all',
      }}
      title={children}
    >
      {text}
    </code>
  );
}

export function EmptyState({ message }: { message: string }): JSX.Element {
  return (
    <div
      style={{
        padding: TOKENS.spacing.xl,
        textAlign: 'center',
        color: TOKENS.color.inkMuted,
        fontStyle: 'italic',
      }}
    >
      {message}
    </div>
  );
}
