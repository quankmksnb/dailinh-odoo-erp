import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// NFR-P01/P02 đo THẬT trên bản đã deploy (https://erp.dailinh.com, qua mạng Internet thật) —
// khác hẳn số liệu "Pass*" trong Report 5.3 (đo trên localhost dlm_dev, không có độ trễ mạng).
// Vẫn chỉ là 1-user (không phải tải đồng thời 50-100 user theo PRD §6.1) — cần k6/JMeter riêng
// cho phần đó, ngoài phạm vi Playwright.

test.describe('NFR-P01/P02 [staging] — role BA/Sales', () => {
  test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

  test('NFR-P01: tải màn Danh sách báo giá qua mạng thật', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await page.getByTitle('Báo giá', { exact: true }).click();
    const start = Date.now();
    await page.locator('div[title="Danh sách báo giá"]').click();
    await expect(page.getByRole('columnheader', { name: 'Số báo giá' })).toBeVisible({ timeout: 15000 });
    const elapsedSec = (Date.now() - start) / 1000;
    console.log(`[staging PERF] NFR-P01 Danh sách báo giá: ${elapsedSec.toFixed(2)}s (mục tiêu PRD §6.1: < 4s, đo 1 user qua mạng thật, không phải 50-100 user đồng thời)`);
    expect(elapsedSec, `Tải Danh sách báo giá mất ${elapsedSec.toFixed(2)}s, vượt mục tiêu 4s`).toBeLessThan(4);
  });

  test('NFR-P02: mở chi tiết báo giá đã có sẵn dữ liệu tính giá', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await page.getByTitle('Báo giá', { exact: true }).click();
    await page.locator('div[title="Danh sách báo giá"]').click();
    await expect(page.getByRole('columnheader', { name: 'Số báo giá' })).toBeVisible({ timeout: 15000 });
    const start = Date.now();
    await page.getByRole('cell', { name: /^BG\// }).first().click();
    await expect(page.getByText('Chi tiết báo giá', { exact: false }).first()).toBeVisible({ timeout: 15000 });
    const elapsedSec = (Date.now() - start) / 1000;
    console.log(`[staging PERF] NFR-P02 Mở chi tiết báo giá (tính giá): ${elapsedSec.toFixed(2)}s (mục tiêu PRD §6.1: < 10s cho 1-20 dòng)`);
    expect(elapsedSec, `Mở chi tiết báo giá mất ${elapsedSec.toFixed(2)}s, vượt mục tiêu 10s`).toBeLessThan(10);
  });
});

test.describe('NFR-P01 [staging] — role Kỹ thuật', () => {
  test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

  test('tải màn BOM sản phẩm qua mạng thật', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await page.getByTitle('Kỹ thuật', { exact: true }).click();
    const start = Date.now();
    await page.locator('div[title="BOM sản phẩm / Bán thành phẩm"]').click();
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
    const elapsedSec = (Date.now() - start) / 1000;
    console.log(`[staging PERF] NFR-P01 BOM sản phẩm: ${elapsedSec.toFixed(2)}s (mục tiêu < 4s)`);
    expect(elapsedSec, `Tải BOM sản phẩm mất ${elapsedSec.toFixed(2)}s, vượt mục tiêu 4s`).toBeLessThan(4);
  });
});
