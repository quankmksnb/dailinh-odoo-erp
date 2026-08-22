import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// SCR-31 Cấu hình Báo giá — trước đây (Lô 2/Lô 7) mới test RBAC menu/tab, CHƯA từng sửa +
// lưu dữ liệu thật bên trong OWL client-action (action=316, dl.pricing.config).
test.describe('SCR-31 - Hao hụt & thu hồi (role: Kỹ thuật) — quy tắc kỹ thuật, áp dụng ngay', () => {
  test.use({ storageState: ROLES.ky_thuat.storageStatePath });

  test('sửa hệ số hao hụt 1 vật tư, lưu ngay không cần duyệt (đúng FDS)', async ({ page }) => {
    await page.goto('/web#action=316&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Hao hụt & thu hồi/ })).toBeVisible({ timeout: 15000 });

    const row = page.locator('tr', { hasText: '[VT-TH-25]' });
    await expect(row).toBeVisible({ timeout: 15000 });
    await row.scrollIntoViewIfNeeded();
    const wasteInput = row.getByRole('spinbutton').first();

    // Đổi sang giá trị chắc chắn khác giá trị hiện tại (tránh trường hợp không đổi thì
    // không bắn API set_dlm_waste, làm waitForResponse treo mãi).
    const current = await wasteInput.inputValue();
    const nextValue = current.trim() === '2.5' ? '2.6' : '2.5';
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/web/dataset/call_kw/product.product/set_dlm_waste')),
      (async () => {
        await wasteInput.fill(nextValue);
        await wasteInput.blur();
      })(),
    ]);
    expect(response.ok()).toBeTruthy();

    // Không có nút "Gửi duyệt" nào xuất hiện cho thay đổi kỹ thuật này — áp dụng ngay.
    await expect(page.getByRole('button', { name: /Gửi duyệt/ })).toHaveCount(0);
  });
});

test.describe('SCR-32 - Cấu hình Hệ thống — KHÔNG tồn tại (mọi vai trò)', () => {
  // BUG (bug-log.md, Critical, đã ghi nhận Lô 6 — làm rõ thêm ở Lô 8): không chỉ là vấn đề
  // RBAC ẩn menu — action "Cấu hình Hệ thống" hoàn toàn KHÔNG tồn tại trong ir_ui_menu (đã
  // query trực tiếp DB dlm_dev: submenu "Cấu hình" chỉ có 4 mục Quản lý User/Phân quyền/
  // Cấu hình Báo giá/Đơn vị tính — không có "Cấu hình Hệ thống" hay "Công ty").
  test.use({ storageState: ROLES.ceo.storageStatePath });

  test.fixme('CEO thấy menu "Cấu hình Hệ thống" trong Cấu hình (theo FDS SCR-32)', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Cấu hình', { exact: true }).click();
    await expect(page.getByTitle('Cấu hình Hệ thống')).toBeVisible();
  });

  test('thực tế: submenu Cấu hình của CEO không có mục "Cấu hình Hệ thống"', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Cấu hình', { exact: true }).click();
    await expect(page.getByTitle('Cấu hình Hệ thống')).toHaveCount(0);
  });
});
