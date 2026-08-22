import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF08-002/004 (Kế toán quản lý bảng giá NCC) đã bỏ khỏi phạm vi test — vai trò Kế toán nội bộ
// không còn tồn tại trong code (dl_base/security/groups.xml không còn định nghĩa nhóm này, trách
// nhiệm giá NCC đã chuyển hẳn sang Mua hàng). Chỉ còn giữ lại BF08-003 (đối chứng RBAC Trưởng KD).
test.describe('BF08-003 (đối chứng RBAC): Trưởng KD mở SCR-07 chỉ đọc', () => {
  test.use({ storageState: STAGING_ROLES.truong_kd.storageStatePath });

  test('Trưởng KD KHÔNG thấy nút "+ Thêm NCC"', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    // Đây là mục rail top-level không có submenu con — bấm thẳng vào title.
    await page.getByTitle('Nhà cung cấp / Thầu phụ', { exact: true }).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Thêm NCC/i })).toHaveCount(0);
    console.log('[staging] BF08-003: Pass — Trưởng KD không thấy nút "+ Thêm NCC" (action chỉ đọc), đúng FDS.');
  });
});
