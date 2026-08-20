import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// 3 case còn "Not Run" trên staging của BF-04 (Report 5.3): TC-E2E-BF04-001 (CEO landing mặc
// định), TC-E2E-BF04-002 (CEO duyệt yêu cầu mức Giám đốc), TC-E2E-BF04-004 (RBAC: Admin không
// được duyệt). Ngưỡng thật trên staging (đọc qua RPC dl.pricing.approval.matrix): Trưởng KD từ
// 20.000.001đ, Giám đốc từ 100.000.001đ — khác dlm_dev. Dùng số lượng x đơn giá vượt mốc Giám đốc
// để yêu cầu duyệt lên thẳng CEO (không dừng ở Trưởng KD).
test.use({ storageState: STAGING_ROLES.ceo.storageStatePath });

test('TC-E2E-BF04-001 [staging]: CEO đăng nhập, landing mặc định = danh sách Phê duyệt', async ({ page }) => {
  await page.goto('/web');
  await expect(page.getByRole('heading', { name: 'Phê duyệt báo giá' }).or(
    page.getByText('Tổng giá trị chờ', { exact: false })
  )).toBeVisible({ timeout: 20000 });
  await expect(page.locator('.dl-chipbar')).toBeVisible({ timeout: 10000 });
  for (const chip of ['Tất cả', 'Chờ duyệt', 'Đã duyệt', 'Từ chối', 'Đã hủy']) {
    await expect(page.locator('.dl-chip .dl-chip-label', { hasText: chip })).toBeVisible({ timeout: 10000 });
  }
  await expect(page.getByText('Tổng giá trị chờ', { exact: false })).toBeVisible({ timeout: 10000 });
  console.log('[staging] TC-E2E-BF04-001: CEO landing đúng màn Phê duyệt, đủ 5 chip + Tổng giá trị chờ');
});

test('TC-E2E-BF04-002 + TC-E2E-BF04-004 [staging]: báo giá vượt ngưỡng Giám đốc -> Admin không duyệt được -> CEO duyệt được', async ({ page, browser }) => {
  test.setTimeout(150000);

  // Bước 1 (Sales): tạo báo giá vượt hẳn ngưỡng Giám đốc (100.000.001đ) — 200 x 850.000 = 170tr.
  const salesCtx = await browser.newContext({ storageState: STAGING_ROLES.sales.storageStatePath });
  const salesPage = await salesCtx.newPage();
  await salesPage.goto('/web');
  await salesPage.getByTitle('Báo giá', { exact: true }).click();
  await salesPage.locator('div[title="Danh sách báo giá"]').click();
  await salesPage.getByRole('button', { name: /Tạo báo giá/ }).click();
  await expect(salesPage.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15000 });

  const customerField = salesPage.locator('input[id^="partner_id_"]');
  await customerField.waitFor({ state: 'visible', timeout: 15000 });
  await customerField.click({ force: true });
  await customerField.fill('Công ty TNHH Cơ khí Việt Thành');
  const customerOption = salesPage.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Công ty TNHH Cơ khí Việt Thành' });
  await customerOption.first().waitFor({ state: 'visible', timeout: 10000 });
  await customerOption.first().click();

  await salesPage.mouse.click(330, 430);
  await salesPage.waitForTimeout(500);
  await salesPage.keyboard.type('Ghế sắt sơn tĩnh điện GS-100 (đơn hàng dự án lớn, test BF04-002/004)');
  await salesPage.keyboard.press('Tab');
  await salesPage.keyboard.type('200');
  await salesPage.keyboard.press('Tab');
  await salesPage.keyboard.type('850000');
  await salesPage.locator('div[name="partner_id"]').first().click();
  await salesPage.getByRole('button', { name: 'Lưu thủ công' }).click();
  await expect.poll(() => salesPage.url(), { timeout: 15000 }).toMatch(/[?&#]id=\d+/);
  const quoteCode = await salesPage.locator('.o_breadcrumb, .o_last_breadcrumb_item').last().innerText();
  console.log(`[staging] Đã tạo báo giá ${quoteCode} (850.000đ x 200 = 170.000.000đ, vượt ngưỡng Giám đốc 100.000.001đ)`);

  // Chạm lại Chiết khấu để kích hoạt đánh giá lại (create() không tự reevaluate — GAP đã ghi
  // nhận ở stg-bf04-approval-flow.spec.ts).
  await salesPage.locator('div[name="discount_pct"] input').last().fill('1');
  await salesPage.keyboard.press('Tab');
  await salesPage.getByRole('button', { name: 'Lưu thủ công' }).click().catch(() => {});
  await salesPage.waitForTimeout(1500);
  await salesPage.reload();
  await expect(salesPage.getByText('Báo giá cần phê duyệt', { exact: false }).first()).toBeVisible({ timeout: 15000 });
  console.log(`[staging] ${quoteCode}: đã chuyển Chờ phê duyệt (mức Giám đốc)`);
  await salesCtx.close();

  // Tra ID yêu cầu duyệt đang pending cho báo giá này (dùng session CEO của test chính).
  const reqLookup = await page.request.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: {
        model: 'dl.pricing.approval.request', method: 'search_read',
        args: [[['object_label', '=', quoteCode], ['state', '=', 'pending']], ['id', 'request_type']],
        kwargs: { limit: 1 },
      },
    },
  }).then((r) => r.json()).then((b) => b.result?.[0]);
  expect(reqLookup, `không tìm thấy yêu cầu duyệt pending cho ${quoteCode}`).toBeTruthy();
  console.log(`[staging] Yêu cầu duyệt #${reqLookup.id} (${reqLookup.request_type}) đang pending`);

  // Bước 2 (Admin/IT) — TC-E2E-BF04-004: mở đúng yêu cầu này, xác nhận KHÔNG có nút Duyệt.
  const adminCtx = await browser.newContext({ storageState: STAGING_ROLES.admin_it.storageStatePath });
  const adminPage = await adminCtx.newPage();
  await adminPage.goto(`/web#id=${reqLookup.id}&model=dl.pricing.approval.request&view_type=form&cids=1`);
  await expect(adminPage.locator('.o_form_view')).toBeVisible({ timeout: 15000 });
  await expect(adminPage.getByRole('button', { name: 'Phê duyệt' })).toHaveCount(0, { timeout: 10000 });
  console.log('[staging] TC-E2E-BF04-004: Admin/IT mở đúng yêu cầu, xác nhận không thấy nút Duyệt (RBAC đúng)');
  await adminCtx.close();

  // Bước 3 (CEO, session chính của test) — TC-E2E-BF04-002: duyệt yêu cầu.
  await page.goto(`/web#id=${reqLookup.id}&model=dl.pricing.approval.request&view_type=form&cids=1`);
  await expect(page.getByRole('button', { name: 'Phê duyệt' })).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Phê duyệt' }).click();
  const confirmDialog = page.getByRole('dialog').filter({ hasText: 'Xác nhận' });
  await expect(confirmDialog).toBeVisible({ timeout: 10000 });
  await confirmDialog.getByRole('button', { name: 'Ok' }).click();
  await expect(confirmDialog).toBeHidden({ timeout: 10000 });
  await expect(page.getByRole('button', { name: 'Phê duyệt' })).toHaveCount(0, { timeout: 15000 });
  console.log(`[staging] TC-E2E-BF04-002: CEO đã duyệt yêu cầu #${reqLookup.id} cho ${quoteCode}`);

  // Xác nhận báo giá liên kết đã chuyển Đã phê duyệt (đủ điều kiện chuyển sang BF-05).
  const quoteState = await page.request.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: {
        model: 'dl.quotation', method: 'search_read',
        args: [[['name', '=', quoteCode]], ['approval_state']], kwargs: { limit: 1 },
      },
    },
  }).then((r) => r.json()).then((b) => b.result?.[0]);
  expect(quoteState?.approval_state, `${quoteCode} phải chuyển approval_state=approved sau khi CEO duyệt`).toBe('approved');
  console.log(`[staging] ${quoteCode}: approval_state = ${quoteState.approval_state} — đúng luồng BF-04, sẵn sàng BF-05`);
});
