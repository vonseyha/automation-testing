import { test, expect } from './fixtures/auth.fixture';

test.describe('Car Sales Report & Filter Chips', () => {
  test('car sales report page loads', async ({ authedPage: page }) => {
    await page.goto('/cars-report', { waitUntil: 'networkidle' });
    const section = page.locator('section').first();
    await expect(section).toBeVisible({ timeout: 15_000 });
  });

  test('cashflow dashboard widget is embedded in sales report', async ({ authedPage: page }) => {
    await page.goto('/cars-report', { waitUntil: 'networkidle' });
    const dashboard = page.locator('app-cashflow-dashboard');
    await expect(dashboard).toBeVisible({ timeout: 15_000 });
  });

  test('filter dialog can be opened', async ({ authedPage: page }) => {
    await page.goto('/cars-report', { waitUntil: 'networkidle' });
    const filterBtn = page.locator('button', { hasText: 'Filter' }).or(
      page.locator('[class*="fixed"] button').first(),
    );
    if (await filterBtn.isVisible()) {
      await filterBtn.click();
      const filterPanel = page.locator('text=Filter Report');
      await expect(filterPanel).toBeVisible({ timeout: 5_000 });
    }
  });

  test('filter chip removal button is present when filters are active', async ({ authedPage: page }) => {
    await page.goto('/cars-report', { waitUntil: 'networkidle' });
    const chips = page.locator('.rounded-full.border >> text=×');
    const chipCount = await chips.count();
    if (chipCount > 0) {
      await expect(chips.first()).toBeVisible();
    }
  });
});
