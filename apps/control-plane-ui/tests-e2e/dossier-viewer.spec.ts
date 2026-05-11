/**
 * Playwright E2E — Dossier viewer (CP-21).
 *
 * The seed pre-generates a SignedDossier for decision B. We
 * discover its dossier_id by hitting the API directly (the
 * dossier_id isn't currently surfaced anywhere on a UI page;
 * Phase-1 will add a "Generate dossier" client-side flow on the
 * decision detail page that returns the id).
 *
 * Strategy for finding the seeded dossier:
 *   1. Use the API to list workflows + pull audit_ids.
 *   2. Generate a fresh dossier for the triad decision; we can
 *      use its dossier_id to drive the UI test. (The seeded one
 *      is reachable via the same /v1/control/dossier endpoint
 *      but its id isn't exposed -- generating a new one is the
 *      cheapest way to get a working URL.)
 */

import { expect, test } from '@playwright/test';

interface AuditEntry {
  audit_id: string;
  triad_invoked: boolean;
}

async function generateDossierForTriadDecision(
  page: import('@playwright/test').Page,
): Promise<string> {
  const wfResp = await page.request.get(
    'http://127.0.0.1:8001/v1/control/workflows',
  );
  const wf = await wfResp.json();
  const workflowId = wf.workflows[0].workflow_id as string;

  const now = new Date();
  const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  const auditResp = await page.request.get(
    `http://127.0.0.1:8001/v1/control/audit?workflow_id=${workflowId}` +
      `&from=${monthAgo.toISOString()}&to=${now.toISOString()}`,
  );
  const audit = await auditResp.json();
  const triadEntry = (audit.entries as AuditEntry[]).find(
    (e) => e.triad_invoked,
  );
  expect(triadEntry).toBeDefined();

  const genResp = await page.request.post(
    'http://127.0.0.1:8001/v1/control/dossier',
    {
      data: {
        audit_id: triadEntry!.audit_id,
        action_summary: 'e2e test dossier',
      },
    },
  );
  expect(genResp.ok()).toBeTruthy();
  const gen = await genResp.json();
  return gen.dossier_id as string;
}

test.describe('Dossier viewer (/dossier/[dossier_id])', () => {
  test('renders all four manifest sections for a real dossier', async ({
    page,
  }) => {
    const dossierId = await generateDossierForTriadDecision(page);
    await page.goto(`/dossier/${dossierId}`);

    await expect(
      page.getByRole('heading', { name: 'Signed dossier' }),
    ).toBeVisible();

    // Section 1: Cover.
    await expect(page.locator('text=Cover').first()).toBeVisible();
    await expect(page.locator('text=Dossier ID').first()).toBeVisible();
    await expect(page.locator('text=Audit ID').first()).toBeVisible();
    await expect(page.locator('text=Action summary').first()).toBeVisible();
    await expect(page.locator('text=e2e test dossier').first()).toBeVisible();

    // Section 2: Decision trail.
    await expect(
      page.locator('text=Decision trail').first(),
    ).toBeVisible();
    await expect(
      page.locator('text=Policy evaluations').first(),
    ).toBeVisible();
    await expect(
      page.locator('text=Triad consensus').first(),
    ).toBeVisible();

    // Section 3: Evidence.
    await expect(page.locator('text=Evidence').first()).toBeVisible();
    await expect(
      page.locator('text=Retrieved documents').first(),
    ).toBeVisible();

    // Section 4: Crypto proof + Download.
    await expect(
      page.locator('text=Crypto proof').first(),
    ).toBeVisible();
    await expect(
      page.locator('text=Signature (Ed25519, 128 hex chars)').first(),
    ).toBeVisible();
    await expect(
      page.locator('text=Public key (Ed25519, 64 hex chars)').first(),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /Download dossier as JSON/ }),
    ).toBeVisible();
  });

  test('signature is exactly 128 hex chars and public key is 64', async ({
    page,
  }) => {
    const dossierId = await generateDossierForTriadDecision(page);
    await page.goto(`/dossier/${dossierId}`);

    // Two MonoBlock <pre> elements: signature + public key.
    const blocks = page.locator('pre');
    const blockCount = await blocks.count();
    expect(blockCount).toBeGreaterThanOrEqual(2);

    // Find the signature + pubkey by their preceding subhead.
    const sigText = await page
      .locator('h3:has-text("Signature") + pre')
      .first()
      .innerText();
    expect(sigText.trim()).toHaveLength(128);
    expect(sigText.trim()).toMatch(/^[0-9a-f]{128}$/);

    const pkText = await page
      .locator('h3:has-text("Public key") + pre')
      .first()
      .innerText();
    expect(pkText.trim()).toHaveLength(64);
    expect(pkText.trim()).toMatch(/^[0-9a-f]{64}$/);
  });

  test('download link points at a data: URI carrying the JSON', async ({
    page,
  }) => {
    const dossierId = await generateDossierForTriadDecision(page);
    await page.goto(`/dossier/${dossierId}`);

    const link = page.getByRole('link', {
      name: /Download dossier as JSON/,
    });
    const href = await link.getAttribute('href');
    expect(href).not.toBeNull();
    expect(href!.startsWith('data:application/json')).toBe(true);
    // The encoded JSON contains the dossier_id we navigated to.
    expect(decodeURIComponent(href!)).toContain(dossierId);
  });

  test('404 path renders Dossier not found card', async ({ page }) => {
    await page.goto('/dossier/00000000-0000-0000-0000-000000000000');
    await expect(
      page.locator('text=Dossier not found').first(),
    ).toBeVisible();
  });
});
