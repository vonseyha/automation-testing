import { test, expect } from '@playwright/test';
import { loginViaAPI, injectAuth } from './fixtures/auth.fixture';

const BASE = process.env.BASE_URL || 'http://localhost:4200';

test.describe('Authentication & Route Guards', () => {
  test('login page renders with phone and password fields', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await expect(page.locator('#phoneNumber')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('invalid credentials show error feedback', async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await page.fill('#phoneNumber', '999999999');
    await page.fill('#password', 'wrong-password');
    await page.click('button[type="submit"]');
    const sweetAlert = page.locator('.swal2-popup');
    await expect(sweetAlert).toBeVisible({ timeout: 10_000 });
  });

  test('unauthenticated access to protected route redirects to /login', async ({ page }) => {
    await page.goto(`${BASE}/cashflow-dashboard`, { waitUntil: 'networkidle' });
    await expect(page).toHaveURL(/\/login/);
  });

  test('authenticated user can access dashboard (root route)', async ({ page }) => {
    const token = await loginViaAPI(page);
    await injectAuth(page, token);
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.locator('header')).toBeVisible();
  });
});
