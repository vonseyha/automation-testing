import { test, expect } from './fixtures/auth.fixture';

test.describe('Dashboard & Navigation', () => {
  test('dashboard loads with navigation header', async ({ authedPage: page }) => {
    await expect(page.locator('header')).toBeVisible();
    const logo = page.locator('header img[alt="Company Logo"]');
    await expect(logo).toBeVisible();
  });

  test('Navigate menu opens and shows menu groups', async ({ authedPage: page }) => {
    const navButton = page.locator('button', { hasText: 'Navigate' });
    await expect(navButton).toBeVisible();
    await navButton.click();
    const menuGroups = page.locator('.rounded-xl.border.border-slate-100');
    await expect(menuGroups.first()).toBeVisible({ timeout: 5_000 });
    const groupCount = await menuGroups.count();
    expect(groupCount).toBeGreaterThanOrEqual(5);
  });

  test('dashboard renders at least one card widget', async ({ authedPage: page }) => {
    const cards = page.locator('.grid .bg-white.rounded.shadow');
    await expect(cards.first()).toBeVisible({ timeout: 15_000 });
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
