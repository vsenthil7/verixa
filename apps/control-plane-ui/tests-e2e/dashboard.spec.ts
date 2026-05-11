/**
 * Playwright E2E — Dashboard page (CP-21).
 *
 * Hits the live UI against the seeded FastAPI and asserts the
 * demo workflow + audit history render correctly.
 */

import { expect, test } from '@playwright/test';

test.describe('Dashboard page (/)', () => {
  test('renders the Verixa header and dashboard title', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('text=Verixa Control Plane')).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Dashboard' }),
    ).toBeVisible();
  });

  test('shows the seeded loan-approval workflow card', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: 'Loan Approval Workflow' }),
    ).toBeVisible();
    // The workflow's KeyValueRow fields are all present.
    await expect(page.locator('text=Workflow ID').first()).toBeVisible();
    await expect(page.locator('text=Sector').first()).toBeVisible();
    await expect(
      page.locator('text=financial-services').first(),
    ).toBeVisible();
    // Risk threshold escalation seeded at 0.40 -> '40%'.
    await expect(page.locator('text=40%').first()).toBeVisible();
    // Exactly 1 agent registered.
    await expect(page.locator('text=Registered agents').first()).toBeVisible();
  });

  test('lists the three seeded historical decisions', async ({ page }) => {
    await page.goto('/');
    // Decision A: allow + low. Decision B: allow + medium + triad.
    // Decision C: deny + critical. Pill text is uppercase via CSS;
    // search the rendered text which is unchanged.
    const pillsAllow = page.locator('table').getByText('allow', { exact: true });
    await expect(pillsAllow.first()).toBeVisible();
    const pillsDeny = page.locator('table').getByText('deny', { exact: true });
    await expect(pillsDeny.first()).toBeVisible();
    // Triad column: at least one 'yes' (decision B) and one 'no'.
    await expect(page.locator('text=yes').first()).toBeVisible();
    await expect(page.locator('text=no').first()).toBeVisible();
  });

  test('audit ID links go to /decisions/<id>', async ({ page }) => {
    await page.goto('/');
    // The first audit-id link in the recent-decisions table.
    const firstLink = page
      .locator('table a[href^="/decisions/"]')
      .first();
    await expect(firstLink).toBeVisible();
    const href = await firstLink.getAttribute('href');
    expect(href).toMatch(/^\/decisions\/[0-9a-f-]{36}$/);
  });

  test('"View full audit log" footer links to /audit?workflow_id=...', async ({
    page,
  }) => {
    await page.goto('/');
    const link = page.locator('a[href^="/audit?workflow_id="]');
    await expect(link).toBeVisible();
    const href = await link.getAttribute('href');
    expect(href).toMatch(/^\/audit\?workflow_id=[0-9a-f-]{36}$/);
  });
});
