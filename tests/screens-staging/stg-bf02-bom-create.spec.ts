import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF-02 BOM Creation & Management — Kỹ thuật tạo BOM mới cho 1 sản phẩm tự sản xuất, thêm 1
// dòng vật tư có sẵn (staging đã có sẵn danh mục vật tư thép/phụ kiện thật, không cần tự tạo).
test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

test('BF-02: Kỹ thuật tạo BOM mới cho sản phẩm tự sản xuất, thêm dòng vật tư', async ({ page }) => {
  test.setTimeout(60000);
  await page.goto('/web');
  await page.getByTitle('Kỹ thuật', { exact: true }).click();
  await page.locator('div[title="BOM sản phẩm / Bán thành phẩm"]').click();
  await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: /Mới/ }).click();

  // Chọn Sản phẩm (many2one) — sản phẩm tự sản xuất có sẵn trên staging (VD "Khung thép hàn CT-200").
  await page.getByLabel('Sản phẩm', { exact: true }).click();
  const productOption = page.locator('.o-autocomplete--dropdown-menu li').first();
  await productOption.waitFor({ state: 'visible', timeout: 15000 });
  await productOption.click();

  // Thêm 1 dòng vật tư — mở dialog "Tạo Danh sách vật tư" (đúng theo pattern đã xác nhận ổn định
  // ở dlm_dev: tests/screens/scr-14-15-bom-create.spec.ts).
  await page.getByRole('button', { name: /Thêm.*dòng/i }).first().click();
  const lineDialog = page.getByRole('dialog').filter({ hasText: 'Tạo Danh sách vật tư' });
  const materialField = lineDialog.getByLabel('Vật tư', { exact: true });
  await materialField.waitFor({ state: 'visible', timeout: 15000 });
  // Click rồi chọn thẳng option đầu (không gõ tìm kiếm trước) liên tục thất bại trên staging dù
  // hoạt động ổn định ở dlm_dev cục bộ (field vẫn trống sau khi chọn, kể cả bằng bàn phím
  // ArrowDown+Enter) — thử gõ tên vật tư cụ thể để lọc dropdown còn đúng 1 kết quả trước khi
  // click, giống cách đã ổn định ở test BF-04 (chọn khách hàng/sản phẩm trên báo giá).
  await materialField.click();
  await materialField.pressSequentially('Thép hộp chữ nhật 100', { delay: 50 });
  const materialOption = page.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Thép hộp chữ nhật 100' });
  await materialOption.first().waitFor({ state: 'visible', timeout: 15000 });
  await materialOption.first().click();
  await expect(materialField).not.toHaveValue('', { timeout: 10000 });
  await lineDialog.getByRole('button', { name: 'Lưu & Đóng' }).click();

  await page.getByRole('button', { name: 'Lưu thủ công' }).click();

  await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('New', { timeout: 15000 });
  await expect(page.getByText('Nháp', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: /Xác nhận BOM/ })).toBeVisible();
  const bomCode = await page.getByRole('heading', { level: 1 }).innerText();
  console.log(`[staging] Kỹ thuật đã tạo BOM ${bomCode} với 1 dòng vật tư thật`);
});
