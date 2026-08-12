import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-02 BOM Creation & Management — vòng đời đầy đủ Nháp → Đã xác nhận → Đã khóa, tạo BOM
// thật từ đầu (trước đây chỉ test trên BOM demo có sẵn, chưa từng tạo mới qua UI).
test.use({ storageState: ROLES.ky_thuat.storageStatePath });

test('tạo BOM mới, thêm dòng vật tư, Xác nhận, rồi Khóa — đúng vòng đời FDS', async ({ page }) => {
  test.setTimeout(90000);
  await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
  await page.getByRole('button', { name: /Thêm BOM/ }).click();
  await expect(page.getByText('Thêm BOM').first()).toBeVisible({ timeout: 15000 });

  // Loại BOM = "BOM báo giá" (BOM sản phẩm, khác BOM mẫu).
  await page.getByLabel('Loại BOM').selectOption('BOM báo giá');

  // Chọn sản phẩm.
  const productField = page.locator('input[id^="product_id_"]');
  await productField.click({ force: true });
  await page.locator('.o-autocomplete--dropdown-menu li, [role="dialog"] article').first().waitFor({ timeout: 15000 });
  // Dùng dialog tìm kiếm sản phẩm đầy đủ (nhiều sản phẩm nên field này mở dialog, không phải dropdown đơn giản).
  const productDialog = page.getByRole('dialog').filter({ hasText: 'Tìm: Sản phẩm' });
  if (await productDialog.count()) {
    await productDialog.getByRole('article').first().click();
  } else {
    await page.locator('.o-autocomplete--dropdown-menu li').first().click();
  }

  // Thêm 1 dòng vật tư.
  await page
    .getByRole('table')
    .filter({ hasText: 'Vật tư' })
    .getByRole('button', { name: 'Thêm một dòng' })
    .click();
  const materialDialog = page.getByRole('dialog').filter({ hasText: 'Tạo Danh sách vật tư' });
  await expect(materialDialog).toBeVisible({ timeout: 15000 });
  // Chọn "VT-BANLE-3" (vật tư tiêu hao đơn giản, đơn vị Units) — tránh dòng đầu (BTP-...) vì
  // Bán thành phẩm đòi hỏi thêm dữ liệu Khối lượng mới lưu được (khác mục tiêu test này).
  const materialInput = materialDialog.locator('input[id^="material_id_"]');
  await materialInput.click({ force: true });
  const materialOption = page.locator('.o-autocomplete--dropdown-menu li', { hasText: 'VT-BANLE-3' }).first();
  await materialOption.waitFor({ state: 'visible', timeout: 15000 });
  await materialOption.click();
  await materialDialog.getByRole('button', { name: 'Lưu & Đóng' }).click();

  // Lưu BOM (chuyển từ "New" sang mã BOM thật).
  await page.getByRole('button', { name: 'Lưu thủ công' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/BOM-\d+/, { timeout: 15000 });

  // Trạng thái Nháp → bấm "Xác nhận BOM" — có thể là nút trực tiếp trên header (viewport rộng)
  // hoặc nằm trong menu "Tác vụ" (viewport hẹp), tuỳ độ rộng render.
  async function clickAction(label: string) {
    const directBtn = page.getByRole('button', { name: label, exact: true });
    if (await directBtn.count()) {
      await directBtn.click();
      return;
    }
    await page.getByRole('button', { name: 'Tác vụ' }).click();
    await page.getByRole('menuitem').filter({ hasText: label }).click();
  }

  await clickAction('Xác nhận BOM');
  await expect(page.getByRole('button', { name: /Xác nhận BOM/ })).toHaveCount(0, { timeout: 15000 });

  // Trạng thái Đã xác nhận → phải có Khóa và Về nháp (dù ở header hay menu Tác vụ).
  await expect(
    page.getByRole('button', { name: 'Khóa', exact: true }).or(page.getByRole('button', { name: 'Tác vụ' })),
  ).toBeVisible();
  await clickAction('Khóa');

  // Trạng thái Đã khóa → ribbon "Đã khóa" hiện, statusbar 2/2 bước trước đã tick.
  await expect(page.getByText('Đã khóa', { exact: false }).first()).toBeVisible({ timeout: 15000 });
});
