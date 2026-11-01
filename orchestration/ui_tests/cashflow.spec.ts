import { test, expect } from './fixtures/auth.fixture';

test.describe('Cashflow Command Center', () => {
  test('cashflow dashboard page loads and shows charts', async ({ authedPage: page }) => {
    await page.goto('/cashflow-dashboard', { waitUntil: 'networkidle' });
    const section = page.locator('section').first();
    await expect(section).toBeVisible({ timeout: 15_000 });
  });

  test('revenue chart section is rendered', async ({ authedPage: page }) => {
    await page.goto('/cashflow-dashboard', { waitUntil: 'networkidle' });
    const revenueHeading = page.locator('h3', { hasText: 'ទិដ្ឋភាពទូទៅប្រាក់ចំណូល' }).or(
      page.locator('h3', { hasText: 'ចំណូល' }),
    );
    await expect(revenueHeading.first()).toBeVisible({ timeout: 15_000 });
  });

  test('sales by model chart section is rendered', async ({ authedPage: page }) => {
    await page.goto('/cashflow-dashboard', { waitUntil: 'networkidle' });
    const modelHeading = page.locator('h3', { hasText: 'លក់តាមម៉ូដែល' }).or(
      page.locator('h3', { hasText: 'ម៉ូដែល' }),
    );
    await expect(modelHeading.first()).toBeVisible({ timeout: 15_000 });
  });
});
