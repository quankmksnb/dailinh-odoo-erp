import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF-10 Inventory Management — Thủ kho tạo phiếu Nhận hàng NCC thật, xác nhận, rồi mở phiếu
// Kiểm & cất hàng tự sinh, "Đạt tất cả" để cất vào kho. Dùng NCC + vật tư thép thật đã có sẵn
// trên staging (không cần tự tạo thêm).
const SUPPLIER = 'Cong ty TNHH Thep Mien Nam';
const MATERIAL = 'Thép tấm CT3 dày';

test.use({ storageState: STAGING_ROLES.thu_kho.storageStatePath });

test('BF-10: Thủ kho nhận hàng NCC, kiểm & cất hàng vào kho', async ({ page }) => {
  test.setTimeout(120000);

  await page.goto('/web');
  await page.getByTitle('Kho', { exact: true }).click();
  await page.locator('div[title="Nhận hàng"]').click();
  await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: /Mới/ }).click();
  await expect(page.getByText('Nhận hàng nhà cung cấp', { exact: false }).first()).toBeVisible({ timeout: 15000 });

  const supplierField = page.locator('div[name="partner_id"] input').first();
  await supplierField.click({ force: true });
  await supplierField.pressSequentially(SUPPLIER, { delay: 30 });
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().waitFor({ timeout: 15000 });
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().click();

  await page.getByRole('button', { name: 'Thêm một dòng' }).click();
  const selectedRow = page.locator('.o_selected_row').first();
  const productInput = selectedRow.locator('div[name="product_id"] input');
  await productInput.click({ force: true });
  await productInput.pressSequentially(MATERIAL, { delay: 30 });
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().waitFor({ timeout: 15000 });
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().click();
  await selectedRow.locator('div[name="product_uom_qty"] input').fill('50');

  await page.getByRole('button', { name: 'Lưu thủ công' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/NH\/|\/NH\//, { timeout: 15000 });
  const docCode = await page.getByRole('heading', { level: 1 }).innerText();
  console.log(`[staging] Đã tạo phiếu Nhận hàng ${docCode} (NCC: ${SUPPLIER}, 50kg ${MATERIAL})`);

  await page.getByRole('button', { name: 'Xác nhận phiếu' }).click();
  await expect(page.getByRole('button', { name: 'Xác nhận nhận hàng' })).toBeVisible({ timeout: 15000 });

  // NFR-P03 [staging]: đo thời gian button_validate (Xác nhận nhận hàng) + action_dlm_validate_qc
  // (Xác nhận kiểm) — 2 bước nghiệp vụ chính của SCR-37/38, điều kiện PRD < 10 giây.
  const tValidateStart = Date.now();
  await page.getByRole('button', { name: 'Xác nhận nhận hàng' }).click();
  await expect(page.getByRole('button', { name: 'Mở phiếu kiểm' })).toBeVisible({ timeout: 20000 });
  const tValidate = (Date.now() - tValidateStart) / 1000;
  console.log(`[staging] ${docCode}: đã xác nhận nhận hàng (button_validate), tự sinh phiếu kiểm — ${tValidate.toFixed(3)}s`);

  await page.getByRole('button', { name: 'Mở phiếu kiểm' }).click();
  await expect(page.getByText('Kiểm & cất hàng').first()).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Đạt tất cả' }).click();
  await expect(page.getByRole('button', { name: 'Xác nhận kiểm' })).toBeEnabled({ timeout: 15000 });

  const tQcStart = Date.now();
  await page.getByRole('button', { name: 'Xác nhận kiểm' }).click();
  await expect(page.getByText('Đã cất').first()).toBeVisible({ timeout: 20000 });
  const tQc = (Date.now() - tQcStart) / 1000;
  await expect(page.locator('.alert-danger')).toHaveCount(0);
  const total = tValidate + tQc;
  console.log(`[staging] ${docCode}: Đạt tất cả -> Đã cất vào kho thành công (action_dlm_validate_qc: ${tQc.toFixed(3)}s), không còn cảnh báo đỏ`);
  console.log(`[staging] NFR-P03 tổng: button_validate ${tValidate.toFixed(3)}s + action_dlm_validate_qc ${tQc.toFixed(3)}s = ${total.toFixed(3)}s (điều kiện PRD < 10s)`);

  const fs = require('fs');
  fs.writeFileSync(
    'tests/reports/perf-results-staging-nfr-p03.json',
    JSON.stringify({ validate_seconds: tValidate, qc_seconds: tQc, total_seconds: total }, null, 2),
    'utf-8',
  );
  expect(total).toBeLessThan(10);
});
