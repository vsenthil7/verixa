/**
 * Playwright E2E — Decision detail page (CP-21).
 *
 * Picks the triad-bearing decision (B) from the seeded data and
 * confirms the full replay bundle renders: summary, request
 * envelope JSON, policy evaluations table, triad verdicts +
 * commitments.
 */

import { expect, test } from '@playwright/test';

interface AuditEntry {
  audit_id: string;
  decision: string;
  risk_classification: string;
  triad_invoked: boolean;
  timestamp: string;
}

async function getTriadAuditId(
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
  return triadEntry!.audit_id;
}

test.describe('Decision detail (/decisions/[audit_id])', () => {
  test('summary card shows decision + risk + timestamp', async ({ page }) => {
    const auditId = await getTriadAuditId(page);
    await page.goto(`/decisions/${auditId}`);
    await expect(
      page.getByRole('heading', { name: 'Decision detail' }),
    ).toBeVisible();
    await expect(page.locator('text=Summary').first()).toBeVisible();
    await expect(page.locator('text=Audit ID').first()).toBeVisible();
    await expect(page.locator('text=Tenant ID').first()).toBeVisible();
    await expect(page.locator('text=Decision').first()).toBeVisible();
    // Decision B is allow + medium-risk.
    await expect(
      page.locator('text=allow', { hasText: 'allow' }).first(),
    ).toBeVisible();
    await expect(
      page.locator('text=medium', { hasText: 'medium' }).first(),
    ).toBeVisible();
  });

  test('request envelope is rendered as JSON', async ({ page }) => {
    const auditId = await getTriadAuditId(page);
    await page.goto(`/decisions/${auditId}`);
    await expect(
      page.locator('text=Request envelope').first(),
    ).toBeVisible();
    // The seeded request envelope action.tool_name is transfer_funds.
    await expect(
      page.locator('pre').filter({ hasText: 'transfer_funds' }),
    ).toBeVisible();
  });

  test('policy evaluations table shows the two seeded passes', async ({
    page,
  }) => {
    const auditId = await getTriadAuditId(page);
    await page.goto(`/decisions/${auditId}`);
    await expect(
      page
        .locator('text=Policy evaluations')
        .first(),
    ).toBeVisible();
    // Both seeded policies for decision B:
    await expect(
      page.locator('text=verixa.fs.transfer_limit'),
    ).toBeVisible();
    await expect(
      page.locator('text=verixa.fs.beneficiary_verification'),
    ).toBeVisible();
  });

  test('triad review card renders with 3 verdicts + 3 commitments', async ({
    page,
  }) => {
    const auditId = await getTriadAuditId(page);
    await page.goto(`/decisions/${auditId}`);

    await expect(page.locator('text=Triad review').first()).toBeVisible();
    await expect(page.locator('text=Consensus kind').first()).toBeVisible();
    await expect(page.locator('text=majority').first()).toBeVisible();

    // 3 reviewers, each appears under verdicts + commitments.
    for (const rid of ['reviewer_a', 'reviewer_b', 'reviewer_c']) {
      // Each reviewer_id shows up at least twice
      // (verdicts table + commitments table).
      const occurrences = page.locator(`text=${rid}`);
      const count = await occurrences.count();
      expect(count).toBeGreaterThanOrEqual(2);
    }
  });

  test('404 path renders Audit not found card', async ({ page }) => {
    // Random unseeded UUID -> ApiError 404 -> "Audit not found" card.
    await page.goto('/decisions/00000000-0000-0000-0000-000000000000');
    await expect(page.locator('text=Audit not found').first()).toBeVisible();
  });
});
