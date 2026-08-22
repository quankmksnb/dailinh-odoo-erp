import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-10 Inventory Management — SCR-36 (Hàng đợi phiếu), SCR-37 (Nhận hàng NCC),
// SCR-38 (Kiểm & cất hàng), SCR-39 (Trả hàng NCC).
// UC-074/075/076. Module dl_inventory (Kho) — trước đây CHƯA có spec L3 nào
// cho phân hệ Kho dù đã có coverage L1/L2 đầy đủ (12 file TransactionCase).
// action_dl_picking_todo=336, action_dl_picking_receipt=334,
// action_dl_picking_qc=335, action_dl_picking_vendor_return=339 (dlm_dev).

const SUPPLIER = 'Cong ty TNHH Thep Mien Nam';
const MATERIAL = 'Thep tam CT3 day 3mm (QA)';

test.describe('SCR-36/37/38 - Nhận hàng NCC + Kiểm & cất hàng (role: Thủ kho)', () => {
  test.use({ storageState: ROLES.thu_kho.storageStatePath });

  test('SCR-36: Hàng đợi phiếu mở được, không lỗi quyền', async ({ page }) => {
    await page.goto('/web#action=336&model=stock.picking&view_type=tree&cids=1&menu_id=205');
    await expect(page.getByText('Hàng đợi phiếu').first()).toBeVisible({ timeout: 15000 });
  });

  test('nhận hàng NCC thật, tự sinh phiếu kiểm, "Đạt tất cả" rồi cất vào kho', async ({ page }) => {
    test.setTimeout(120000);

    // --- SCR-37: tạo phiếu Nhận hàng NCC ---
    await page.goto('/web#action=334&model=stock.picking&view_type=list&cids=1&menu_id=207');
    await page.getByRole('button', { name: /Mới/ }).click();
    await expect(page.getByText('Nhận hàng NCC').first()).toBeVisible({ timeout: 15000 });

    const supplierField = page.locator('div[name="partner_id"] input').first();
    await supplierField.click({ force: true });
    await supplierField.fill(SUPPLIER);
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().waitFor({ timeout: 15000 });
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().click();

    await page.getByRole('button', { name: 'Thêm một dòng' }).click();
    const selectedRow = page.locator('.o_selected_row').first();
    const productInput = selectedRow.locator('div[name="product_id"] input');
    await productInput.click({ force: true });
    await productInput.fill(MATERIAL);
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().waitFor({ timeout: 15000 });
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().click();
    await selectedRow.locator('div[name="product_uom_qty"] input').fill('50');

    await page.getByRole('button', { name: 'Lưu thủ công' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/NH\/|\/NH\//, { timeout: 15000 });

    // Xác nhận phiếu (Nháp -> Chờ nhận).
    await page.getByRole('button', { name: 'Xác nhận phiếu' }).click();
    await expect(page.getByRole('button', { name: 'Xác nhận nhận hàng' })).toBeVisible({ timeout: 15000 });

    // "Thực nhận" đã tự điền = "Dự kiến" (Odoo tiền-điền demand vào quantity
    // khi phiếu chuyển assigned) — không cần sửa tay khi nhận đủ số.
    await expect(page.getByRole('cell', { name: '50,0000' }).first()).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Xác nhận nhận hàng' }).click();
    await expect(page.getByRole('button', { name: 'Mở phiếu kiểm' })).toBeVisible({ timeout: 20000 });

    // --- SCR-38: mở phiếu kiểm tự sinh, "Đạt tất cả" rồi xác nhận kiểm ---
    await page.getByRole('button', { name: 'Mở phiếu kiểm' }).click();
    await expect(page.getByText('Kiểm & cất hàng').first()).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Đạt tất cả' }).click();
    await expect(page.getByRole('button', { name: 'Xác nhận kiểm' })).toBeEnabled({ timeout: 15000 });
    await page.getByRole('button', { name: 'Xác nhận kiểm' }).click();

    // Trạng thái cuối: "Đã cất" (dl_stepper label cho state=done trên form QC).
    await expect(page.getByText('Đã cất').first()).toBeVisible({ timeout: 20000 });
    // Không còn dải đỏ dù có/không có hàng loại (QC-02 ngừng áp dụng sau done).
    await expect(page.locator('.alert-danger')).toHaveCount(0);
  });
});

test.describe('SCR-39 - Trả hàng NCC (role: Mua hàng)', () => {
  test.use({ storageState: ROLES.mua_hang.storageStatePath });

  test('Mua hàng mở được màn Trả hàng NCC, không lỗi quyền', async ({ page }) => {
    await page.goto('/web#action=339&model=stock.picking&view_type=list&cids=1&menu_id=211');
    await expect(page.getByText('Trả hàng NCC').first()).toBeVisible({ timeout: 15000 });
  });
});
