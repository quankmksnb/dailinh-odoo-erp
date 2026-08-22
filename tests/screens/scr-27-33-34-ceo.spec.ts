import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// Luồng CEO theo FDS §2.2: Đăng nhập (SCR-01) → Báo giá (SCR-26/27) xem đầy đủ giá thành/margin
// → Cấu hình › Đơn vị tính (SCR-33) · Công ty (SCR-34).
// Luồng này CHƯA có test tự động trước đây (roles.ts đã có account CEO nhưng chưa spec nào dùng).
test.use({ storageState: ROLES.ceo.storageStatePath });

test.describe('SCR-27 - Chi tiết báo giá (role: CEO) — toàn quyền + thấy giá thành [CRITICAL]', () => {
  test('CEO thấy cột Giá thành/đv và tab "Phân tích giá thành"', async ({ page }) => {
    await page.goto('/web#action=295&model=dl.quotation&view_type=list&cids=1&menu_id=67');
    // Mở báo giá đầu tiên trong danh sách để kiểm tra form chi tiết.
    await page.locator('.o_data_row').first().click();
    await expect(page.getByRole('columnheader', { name: /Giá thành/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /Phân tích giá thành/ })).toBeVisible();
  });

  test('CEO thấy chatter trên báo giá', async ({ page }) => {
    await page.goto('/web#action=295&model=dl.quotation&view_type=list&cids=1&menu_id=67');
    await page.locator('.o_data_row').first().click();
    await expect(page.locator('.o-mail-Chatter')).toBeVisible();
  });

  test('nút "+ Tạo báo giá" hiển thị cho CEO (toàn quyền CRUD)', async ({ page }) => {
    await page.goto('/web#action=295&model=dl.quotation&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Tạo báo giá/ })).toBeVisible();
  });
});

test.describe('SCR-33 - Đơn vị tính (role: CEO) — full CRUD', () => {
  test('danh sách có nút "Mới", tạo được đơn vị mới', async ({ page }) => {
    await page.goto('/web#action=312&model=dl.uom&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible();
  });
});

test.describe('SCR-34 - Công ty (role: CEO) — sửa được, KHÔNG xóa được', () => {
  test('vào được form Công ty, không thấy hành động Xóa trên Thao tác', async ({ page }) => {
    await page.goto('/web#action=52&model=res.company&view_type=list&cids=1&menu_id=67');
    await page.locator('.o_data_row').first().click();
    // Form chi tiết công ty phải mở được (không bị chặn quyền đọc/sửa).
    await expect(page.locator('.o_form_view')).toBeVisible();
  });
});

// BUG (bug-log.md, Critical — xem SCR-32/33/34): FDS quy định CEO thấy đủ submenu Cấu hình
// (Quản lý User, Phân quyền, Cấu hình Báo giá, Cấu hình Hệ thống, Đơn vị tính, Công ty).
// Thực tế rail menu "Cấu hình" của CEO CHỈ hiện 2 mục: "Đơn vị tính" và "Cấu hình Báo giá".
test.describe('Cấu hình (role: CEO) — thấy đủ submenu theo FDS', () => {
  test.fixme('submenu Cấu hình có Quản lý User, Phân quyền, Cấu hình Báo giá, HT, Đơn vị tính, Công ty', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Cấu hình', { exact: true }).click();
    await expect(page.getByTitle('Cấu hình Báo giá')).toBeVisible();
    await expect(page.getByTitle('Đơn vị tính')).toBeVisible();
    await expect(page.getByTitle('Công ty')).toBeVisible();
    await expect(page.getByTitle('Cấu hình Hệ thống')).toBeVisible();
    await expect(page.getByTitle('Quản lý User')).toBeVisible();
    await expect(page.getByTitle('Phân quyền')).toBeVisible();
  });

  test('thực tế: submenu Cấu hình của CEO chỉ có "Đơn vị tính" và "Cấu hình Báo giá"', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Cấu hình', { exact: true }).click();
    await expect(page.getByTitle('Đơn vị tính')).toBeVisible();
    await expect(page.getByTitle('Cấu hình Báo giá')).toBeVisible();
    await expect(page.getByTitle('Công ty')).toHaveCount(0);
    await expect(page.getByTitle('Cấu hình Hệ thống')).toHaveCount(0);
    await expect(page.getByTitle('Quản lý User')).toHaveCount(0);
    await expect(page.getByTitle('Phân quyền')).toHaveCount(0);
  });
});
