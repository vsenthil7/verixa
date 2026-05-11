/**
 * Playwright E2E — Audit log page (CP-21).
 *
 * Two modes:
 *   1. Without workflow_id -> workflow picker.
 *   2. With workflow_id    -> filterable audit table.
 */

import { expect, test } from '@playwright/test';

async function getSeededWorkflowId(
  page: import('@playwright/test').Page,
): Promise<string> {
  // Use the API directly (faster + more reliable than scraping
  // the dashboard) to grab the seeded workflow_id.
  const response = await page.request.get(
    'http://127.0.0.1:8001/v1/control/workflows',
  );
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.total).toBe(1);
  return body.workflows[0].workflow_id as string;
}

test.describe('Audit log page (/audit)', () => {
  test('workflow-picker mode lists seeded workflows', async ({ page }) => {
    await page.goto('/audit');
    await expect(
      page.getByRole('heading', { name: 'Audit Log' }),
    ).toBeVisible();
    // Picker card title.
    await expect(
      page.locator('text=Pick a workflow to inspect').first(),
    ).toBeVisible();
    // The seeded workflow shows up as a clickable row.
    await expect(
      page.getByRole('link', { name: 'Loan Approval Workflow' }),
    ).toBeVisible();
  });

  test('filtered mode shows the three seeded decisions', async ({ page }) => {
    const wfId = await getSeededWorkflowId(page);
    await page.goto(`/audit?workflow_id=${wfId}`);

    // Filter card echoes back workflow + window.
    await expect(page.locator('text=Filter').first()).toBeVisible();
    await expect(page.locator('text=Matches').first()).toBeVisible();

    // Decisions Card with three rows.
    await expect(page.locator('text=Decisions (3)').first()).toBeVisible();

    // Every classification + decision visible at least once.
    await expect(page.locator('text=low').first()).toBeVisible();
    await expect(page.locator('text=medium').first()).toBeVisible();
    await expect(page.locator('text=critical').first()).toBeVisible();
  });

  test('each row links to its decision detail page', async ({ page }) => {
    const wfId = await getSeededWorkflowId(page);
    await page.goto(`/audit?workflow_id=${wfId}`);

    const openLinks = page.locator('a[href^="/decisions/"]');
    await expect(openLinks).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
      const href = await openLinks.nth(i).getAttribute('href');
      expect(href).toMatch(/^\/decisions\/[0-9a-f-]{36}$/);
    }
  });

  test('back-to-dashboard link works', async ({ page }) => {
    const wfId = await getSeededWorkflowId(page);
    await page.goto(`/audit?workflow_id=${wfId}`);
    await page.click('text=← Back to dashboard');
    await expect(
      page.getByRole('heading', { name: 'Dashboard' }),
    ).toBeVisible();
  });
});
