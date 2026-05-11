/**
 * Verixa UI design tokens + small utilities (CP-15.2).
 *
 * Single source of truth for colors, spacing, typography. No
 * Tailwind/shadcn yet — this keeps the diff small and the Phase-0
 * hackathon dependency surface tight. Phase-1 may migrate to
 * shadcn/ui without changing the call-site shape.
 *
 * All helpers below are pure: no React, no DOM. The presentational
 * components live in components/*.tsx and consume these tokens.
 */

export const TOKENS = {
  color: {
    // Verixa palette: deep ink + sea-green accent + risk-tier scales.
    inkBg: '#0B1220', // page background
    inkSurface: '#111A2E', // card background
    inkBorder: '#1F2A44', // card borders / dividers
    inkText: '#E6EAF2', // primary text
    inkMuted: '#8693AE', // secondary text
    accent: '#4FD1C5', // Verixa sea-green
    accentMuted: '#2B7A75',
    // Decision colors mirror the runtime gateway semantics.
    decisionAllow: '#34D399', // green
    decisionDeny: '#F87171', // red
    decisionEscalate: '#FBBF24', // amber
    // Risk classification tier colors.
    riskLow: '#34D399',
    riskMedium: '#FBBF24',
    riskHigh: '#FB923C',
    riskCritical: '#F87171',
  },
  spacing: {
    xs: '0.25rem',
    sm: '0.5rem',
    md: '1rem',
    lg: '1.5rem',
    xl: '2rem',
    xxl: '3rem',
  },
  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
  },
  font: {
    body:
      'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    mono:
      '"JetBrains Mono", "Fira Code", Menlo, Consolas, "Courier New", monospace',
  },
} as const;

/**
 * Map a decision string to its display color. Falls back to muted
 * grey for unknown values (defensive — server should never emit
 * anything outside allow/deny/escalate, but the UI shouldn't crash
 * if it does).
 */
export function decisionColor(decision: string): string {
  switch (decision) {
    case 'allow':
      return TOKENS.color.decisionAllow;
    case 'deny':
      return TOKENS.color.decisionDeny;
    case 'escalate':
      return TOKENS.color.decisionEscalate;
    default:
      return TOKENS.color.inkMuted;
  }
}

/**
 * Map a risk classification string to its display color.
 */
export function riskColor(classification: string): string {
  switch (classification) {
    case 'low':
      return TOKENS.color.riskLow;
    case 'medium':
      return TOKENS.color.riskMedium;
    case 'high':
      return TOKENS.color.riskHigh;
    case 'critical':
      return TOKENS.color.riskCritical;
    default:
      return TOKENS.color.inkMuted;
  }
}

/**
 * Format an ISO-8601 timestamp into a compact UI string like
 * "2026-05-10 11:42 UTC". Falls back to the original string on
 * unparseable input.
 */
export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) {
    return iso;
  }
  const date = d.toISOString().slice(0, 10);
  const time = d.toISOString().slice(11, 16);
  return `${date} ${time} UTC`;
}

/**
 * Format a unix-nanoseconds timestamp into the same compact UI
 * string. Used by the dossier and replay views where the wire
 * carries nanoseconds since epoch.
 */
export function formatTimestampNs(unixNs: number): string {
  return formatTimestamp(new Date(unixNs / 1_000_000).toISOString());
}

/**
 * Format a risk score (0..1) as a percentage string with one
 * decimal place. ``0.4248 -> "42.5%"``.
 */
export function formatRiskScore(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

/**
 * Truncate a UUID string to "first8…last4" for display.
 */
export function shortUuid(uuid: string): string {
  if (uuid.length < 16) {
    return uuid;
  }
  return `${uuid.slice(0, 8)}…${uuid.slice(-4)}`;
}
