import { expect, test } from '@playwright/test';

test('signup, logout, then login lands on home', async ({ page }) => {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const email = `e2e-${suffix}@example.com`;
  const username = `e2e_${suffix}`.slice(0, 30);
  const password = 'correct-horse-battery-staple';

  // Unauthenticated visit to / should redirect to /login.
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);

  // Sign up.
  await page.goto('/signup');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/username/i).fill(username);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign up/i }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole('complementary', { name: /sidebar/i }),
  ).toBeVisible();
  await expect(page.getByText(username)).toBeVisible();

  // Log out returns to /login.
  await page.getByRole('button', { name: /log out/i }).click();
  await expect(page).toHaveURL(/\/login$/);

  // Direct visit to / while unauthenticated still redirects.
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);

  // Log back in with the same credentials.
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /log in/i }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole('complementary', { name: /sidebar/i }),
  ).toBeVisible();
  await expect(page.getByText(username)).toBeVisible();
});
