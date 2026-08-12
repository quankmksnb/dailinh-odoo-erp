import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-01 Customer Request & Product Identification — Alternative Flow A5 (Yêu cầu Sales bổ sung
// thông tin). Trước đây chưa test — chỉ mới có A4 (Không khả thi, scr-25-rfq-wizard.spec.ts).
test('BF-01 A5: Kỹ thuật chọn "Cần bổ sung" → RFQ trả lại Sales, Sales bổ sung & gửi lại', async ({ browser }) => {
  test.setTimeout(90000);
  const salesCtx = await browser.newContext({ storageState: ROLES.sales1.storageStatePath });
  const salesPage = await salesCtx.newPage();

  await salesPage.goto('/web#action=323&model=dl.quotation.request&view_type=form&cids=1');
  await expect(salesPage.getByText('Thêm yêu cầu báo giá').first()).toBeVisible({ timeout: 20000 });
  const customerField = salesPage.locator('input[id^="customer_id_"]');
  await customerField.waitFor({ state: 'visible', timeout: 20000 });
  await customerField.click({ timeout: 15000, force: true });
  const customerOption = salesPage.locator('.o-autocomplete--dropdown-menu li').first();
  await customerOption.waitFor({ state: 'visible', timeout: 20000 });
  await customerOption.click({ timeout: 15000 });

  await salesPage
    .getByRole('table')
    .filter({ hasText: 'Tên sản phẩmNhóm sản phẩmSản' })
    .getByRole('button', { name: 'Thêm một dòng' })
    .click();
  const productName = `Test SCR25 A5 QA ${Date.now()}`;
  await salesPage.getByRole('textbox', { name: 'Tên sản phẩm' }).fill(productName);
  await salesPage.getByRole('textbox', { name: 'Kích thước, yêu cầu kỹ thuật' }).fill('Mô tả sơ sài, thiếu kích thước cụ thể');
  await salesPage.getByRole('button', { name: 'Lưu & Đóng' }).click();
  await salesPage.getByRole('button', { name: 'Lưu thủ công' }).click();

  await expect(salesPage.getByRole('heading', { level: 1 })).not.toHaveText('New', { timeout: 10000 });
  const url = salesPage.url();
  const idMatch = url.match(/[?&#]id=(\d+)/);
  expect(idMatch).not.toBeNull();
  const rfqId = idMatch![1];
  await salesCtx.close();

  const kythuatCtx = await browser.newContext({ storageState: ROLES.ky_thuat.storageStatePath });
  const page = await kythuatCtx.newPage();
  await page.goto(`/web#action=321&id=${rfqId}&cids=1&model=dl.quotation.request&view_type=form`);
  await expect(page.getByText('RFQ này chưa được nhận xử lý')).toBeVisible();
  await page.locator('button[name="action_open_resolve_wizard"]').click();
  await expect(page.getByText('1. Xác định sản phẩm')).toBeVisible();

  await page.getByRole('button', { name: 'Cần bổ sung' }).click();
  const note = 'Thiếu kích thước D x R x C cụ thể, cần Sales xác nhận lại với khách hàng';
  // Dialog "Cần bổ sung" — tìm ô nhập nội dung cần bổ sung (tương tự dialog Không khả thi).
  const supplementDialog = page.getByRole('dialog').filter({ hasText: /bổ sung/i });
  await expect(supplementDialog).toBeVisible({ timeout: 15000 });
  const noteBox = supplementDialog.getByRole('textbox').last();
  await noteBox.fill(note);
  await supplementDialog.getByRole('button', { name: /Xác nhận|Gửi|Yêu cầu/i }).first().click();

  // RFQ chuyển "Trả lại bổ sung", Sales nhận được yêu cầu.
  await expect(page).toHaveURL(/model=dl\.quotation\.request/);
  await kythuatCtx.close();

  // Sales đăng nhập lại, xem RFQ đã bị trả về, có ghi chú cần bổ sung.
  const salesCtx2 = await browser.newContext({ storageState: ROLES.sales1.storageStatePath });
  const salesPage2 = await salesCtx2.newPage();
  await salesPage2.goto(`/web#action=323&id=${rfqId}&cids=1&model=dl.quotation.request&view_type=form`);
  await expect(salesPage2.getByText(/Trả lại bổ sung|cần bổ sung/i).first()).toBeVisible({ timeout: 15000 });
  await salesCtx2.close();
});
