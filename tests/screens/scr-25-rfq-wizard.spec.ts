import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-01 Customer Request & Product Identification — Alternative Flow A4 (Không khả thi).
// SCR-25 (Wizard xử lý dòng RFQ) TRƯỚC ĐÂY chưa có spec nào thao tác thật — các spec cũ
// (scr-22-23-rfq, scr-24-kythuat) chỉ kiểm RBAC xung quanh SCR-24, chưa từng bấm nút "Xử lý".
// Test này dựng dữ liệu thật (Sales tạo RFQ mới) rồi Kỹ thuật xử lý luôn trong cùng 1 test,
// vì wizard cần 1 dòng RFQ ở trạng thái "Mới" — dữ liệu demo hiện có đều đã "confirmed/quoted".
test('BF-01 A4: Sales tạo RFQ gia công → Kỹ thuật mở wizard, kết luận Không khả thi', async ({ browser }) => {
  test.setTimeout(90000);
  const salesCtx = await browser.newContext({ storageState: ROLES.sales1.storageStatePath });
  const salesPage = await salesCtx.newPage();

  await salesPage.goto('/web#action=323&model=dl.quotation.request&view_type=form&cids=1');
  await expect(salesPage.getByText('Thêm yêu cầu báo giá').first()).toBeVisible({ timeout: 20000 });
  // Locator theo id thay vì role/name: field "Khách hàng" (many2one) không liên kết đúng
  // <label for=...> nên getByRole('textbox', {name:'Khách hàng'}) không tìm ra (accessible name rỗng).
  // Field readonly (mở dialog tìm kiếm khi click, không gõ trực tiếp) — cần force click.
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
  const productName = `Test SCR25 Wizard QA ${Date.now()}`;
  await salesPage.getByRole('textbox', { name: 'Tên sản phẩm' }).fill(productName);
  // Mô tả bắt buộc do BUG đã biết (xem bug-log.md, SCR-23 validate ngược) — điền để vượt qua.
  await salesPage.getByRole('textbox', { name: 'Kích thước, yêu cầu kỹ thuật' }).fill('Test wizard SCR-25 QA');
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

  // Mở được wizard SCR-25, đúng 3 bước theo FDS.
  await expect(page.getByText('1. Xác định sản phẩm')).toBeVisible();
  await expect(page.getByText('2. Định mức BOM')).toBeVisible();
  await expect(page.getByText('3. Xác nhận')).toBeVisible();

  await page.getByRole('button', { name: 'Không khả thi' }).click();
  const reason = 'Test QA: không đủ máy móc gia công kích thước này (lý do giả lập cho system test)';
  await page.getByRole('textbox', { name: /Nêu rõ lý do/ }).fill(reason);
  await page.getByRole('button', { name: 'Xác nhận không khả thi' }).click();

  // Đóng wizard, quay về SCR-24 (đúng FDS), RFQ tự chuyển Mới → Đang xử lý → Chờ tạo báo giá
  // (100% dòng đã xử lý, tất cả không khả thi).
  await expect(page).toHaveURL(/model=dl\.quotation\.request/);
  await expect(page.getByText('Tất cả dòng đều được kết luận Không khả thi')).toBeVisible();
  await expect(page.getByText('Đã xử lý 1/1 dòng gia công (1 không khả thi)')).toBeVisible();
  await expect(page.getByText(new RegExp(`Không khả thi.*${reason.slice(0, 20)}`))).toBeVisible();

  await kythuatCtx.close();
});
