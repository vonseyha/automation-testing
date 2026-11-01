import { test as base, expect, Page } from '@playwright/test';

const API_URL = process.env.API_URL || 'http://localhost:3000';
const TEST_PHONE = process.env.TEST_PHONE || '000000000';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'Admin@1234';

export async function loginViaAPI(page: Page): Promise<string> {
  const loginRes = await page.request.post(`${API_URL}/api/auth/login`, {
    data: { phoneNumber: TEST_PHONE, password: TEST_PASSWORD },
  });
  expect(loginRes.ok(), `Login API returned ${loginRes.status()}`).toBeTruthy();

  const body = await loginRes.json();
  expect(body.success, 'Login API did not return success').toBeTruthy();

  const companies = body.companies || [];
  expect(companies.length, 'No companies returned for test user').toBeGreaterThan(0);

  const companyId = companies[0].companyId?._id || companies[0].companyId;
  const selectRes = await page.request.post(`${API_URL}/api/auth/select-company`, {
    headers: { Authorization: `Bearer ${body.preAuthToken}` },
    data: { companyId },
  });
  expect(selectRes.ok(), `Select-company returned ${selectRes.status()}`).toBeTruthy();

  const selectBody = await selectRes.json();
  expect(selectBody.token, 'No JWT token in select-company response').toBeTruthy();

  return selectBody.token;
}

export async function injectAuth(page: Page, token: string): Promise<void> {
  const baseURL = page.url() || (process.env.BASE_URL || 'http://localhost:4200');
  const origin = new URL(baseURL).origin;
  await page.goto(origin, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ tk }) => {
      localStorage.setItem('login-token', tk);
      localStorage.setItem('selectedBranchId', 'ALL');
    },
    { tk: token },
  );
}

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    const token = await loginViaAPI(page);
    await injectAuth(page, token);
    await page.goto('/', { waitUntil: 'networkidle' });
    await use(page);
  },
});

export { expect };
