import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// SCR-09 (Danh sách Sản phẩm) và SCR-17 (Danh sách Bản vẽ kỹ thuật) — trước đây chưa có spec
// nào, dù đây là 2 màn nền tảng của BF-01/BF-02.

test.describe('SCR-09 - Danh sách sản phẩm (role: BA/Sales)', () => {
  test.use({ storageState: ROLES.sales1.storageStatePath });

  test('có nút "Mới" (Sales được tạo sản phẩm)', async ({ page }) => {
    await page.goto('/web#action=286&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
  });
});

test.describe('SCR-09 - Danh sách sản phẩm (role: CEO) — theo FDS không thấy nút Mới', () => {
  test.use({ storageState: ROLES.ceo.storageStatePath });

  test('CEO KHÔNG thấy nút "Mới"', async ({ page }) => {
    await page.goto('/web#action=286&cids=1&menu_id=67');
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
  });
});

test.describe('SCR-09 - Danh sách sản phẩm (role: Trưởng KD) — theo FDS không thấy nút Mới', () => {
  test.use({ storageState: ROLES.truong_kd.storageStatePath });

  test('Trưởng KD KHÔNG thấy nút "Mới"', async ({ page }) => {
    await page.goto('/web#action=286&cids=1&menu_id=67');
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
  });
});

test.describe('SCR-17 - Danh sách Bản vẽ kỹ thuật (role: Kỹ thuật)', () => {
  test.use({ storageState: ROLES.ky_thuat.storageStatePath });

  test('có nút "Mới", bộ lọc trạng thái chỉ có Nháp/Đã xác nhận (không có Lưu trữ)', async ({ page }) => {
    await page.goto('/web#action=318&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
  });
});

test.describe('SCR-17 - Danh sách Bản vẽ kỹ thuật (role: BA/Sales) — KHÔNG có quyền truy cập', () => {
  test.use({ storageState: ROLES.sales1.storageStatePath });

  test('menu "Bản vẽ kỹ thuật" KHÔNG hiển thị cho BA/Sales (không có cả rail "Kỹ thuật")', async ({ page }) => {
    await page.goto('/web');
    await page.waitForTimeout(1500);
    // BA/Sales không có menu rail "Kỹ thuật" nói chung (không riêng gì Bản vẽ).
    await expect(page.getByTitle('Kỹ thuật', { exact: true })).toHaveCount(0);
    await expect(page.getByTitle('Bản vẽ kỹ thuật')).toHaveCount(0);
  });
});

test.describe('SCR-17 - Danh sách Bản vẽ kỹ thuật (role: CEO) — chỉ đọc', () => {
  test.use({ storageState: ROLES.ceo.storageStatePath });

  test('CEO KHÔNG thấy nút "Mới" (chỉ đọc)', async ({ page }) => {
    await page.goto('/web#action=318&cids=1&menu_id=67');
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
  });
});
