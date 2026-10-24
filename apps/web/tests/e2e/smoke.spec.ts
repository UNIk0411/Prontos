import { test, expect } from '@playwright/test';

test('PRONTOS dashboard loads', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Email').fill('admin@prontos.local');
  await page.getByLabel('Password').fill('admin123');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'PRONTOS' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Benchmark report' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Worker pool' })).toBeVisible();
});
