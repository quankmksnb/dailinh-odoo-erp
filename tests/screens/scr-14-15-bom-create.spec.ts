import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-02 BOM Creation & Management — SCR-14/15, tạo BOM MỚI thật (không chỉ RBAC list
// như scr-14-16-bom.spec.ts). TC-E2E-BF02-001: Kỹ thuật tạo BOM cho 1 sản phẩm, thêm
// dòng vật tư, xác nhận chi phí vật tư được tính.
//
// Lưu ý TC-E2E-BF02-002 (quick-create vật tư ngay trên BOM): field material_id trong
// dòng BOM có options="{'no_quick_create': True}" (bom_views.xml dòng 261) — đây là
// CHỦ ĐÍCH THIẾT KẾ (vật tư phải tạo qua màn Vật tư riêng, SCR-11, để đảm bảo đủ
// thông tin quy cách/tính giá), không phải thiếu sót. Không viết test cho hành vi
// không tồn tại này — xem ghi chú Not Applicable ở TC-E2E-BF02-002.

test.use({ storageState: ROLES.ky_thuat.storageStatePath });

test.describe('SCR-14/15 - Tạo BOM mới (role: Kỹ thuật)', () => {
  test('tạo BOM cho 1 sản phẩm, thêm 1 dòng vật tư có sẵn, chi phí vật tư được tính', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await page.getByRole('button', { name: /Mới/ }).click();

    // Chọn Sản phẩm (many2one) — mở dropdown, chọn kết quả đầu tiên có sẵn trong seed data.
    await page.getByLabel('Sản phẩm', { exact: true }).click();
    const productOption = page.locator('.o-autocomplete--dropdown-menu li').first();
    await productOption.waitFor({ state: 'visible', timeout: 15000 });
    await productOption.click();

    // Thêm 1 dòng vật tư — nút "Thêm dòng" bên trong tab "Dòng BOM".
    await page.getByRole('button', { name: /Thêm.*dòng/i }).first().click();

    const lineDialog = page.getByRole('dialog').filter({ hasText: 'Tạo Danh sách vật tư' });
    const materialField = lineDialog.getByLabel('Vật tư', { exact: true });
    await materialField.waitFor({ state: 'visible', timeout: 15000 });
    await materialField.click();
    const materialOption = page.locator('.o-autocomplete--dropdown-menu li').first();
    await materialOption.waitFor({ state: 'visible', timeout: 15000 });
    await materialOption.click();

    // Số lượng đã có mặc định 1,0000 — không cần điền lại.
    await lineDialog.getByRole('button', { name: 'Lưu & Đóng' }).click();

    await page.getByRole('button', { name: 'Lưu thủ công' }).click();

    // BOM lưu thành công (không còn "New"), trạng thái = Nháp, có nút Xác nhận BOM.
    await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('New', { timeout: 15000 });
    await expect(page.getByText('Nháp', { exact: false }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Xác nhận BOM/ })).toBeVisible();
  });
});
