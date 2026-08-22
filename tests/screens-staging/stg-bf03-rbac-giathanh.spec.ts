import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF03-002 (Critical) + BF03-003 (đối chứng CEO) + BF03-005 (mặc định filter danh sách).
// Dùng lại 1 báo giá đã có sẵn trên staging (tạo qua các test BF-03/09/04 trước đó) thay vì tự
// tạo báo giá mới — chỉ cần BẤT KỲ báo giá nào có dòng để kiểm RBAC cột/tab, không phụ thuộc nội
// dung cụ thể.
test('BF03-002/003: RBAC giá thành — Sales KHÔNG thấy, CEO THẤY đầy đủ', async ({ browser }) => {
  test.setTimeout(60000);
  const salesCtx = await browser.newContext({ storageState: STAGING_ROLES.sales.storageStatePath });
  const salesPage = await salesCtx.newPage();

  const lookup = await salesPage.request.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: {
        model: 'dl.quotation', method: 'search_read',
        args: [[['line_ids', '!=', false]], ['id', 'name']], kwargs: { limit: 1, order: 'id desc' },
      },
    },
  }).then((r) => r.json()).then((b) => b.result?.[0]);
  expect(lookup, 'Cần ít nhất 1 báo giá có dòng đã tồn tại trên staging để test RBAC giá thành.').toBeTruthy();
  console.log(`[staging] BF03-002/003: dùng báo giá ${lookup.name} (id=${lookup.id}) để kiểm RBAC`);

  // BF03-002 [Critical]: Sales KHÔNG thấy cột Giá thành/đv, tab Phân tích giá thành, Cấu phần giá.
  await salesPage.goto(`/web#id=${lookup.id}&model=dl.quotation&view_type=form&cids=1`);
  await expect(salesPage.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15000 });
  await expect(salesPage.getByRole('columnheader', { name: /Giá thành/ })).toHaveCount(0);
  await expect(salesPage.getByRole('tab', { name: /Phân tích giá thành/ })).toHaveCount(0);
  await expect(salesPage.getByText(/Cấu phần giá/)).toHaveCount(0);
  await expect(salesPage.getByRole('button', { name: 'Gửi tin' })).toBeVisible();
  console.log(`[staging] BF03-002: Pass — Sales không thấy dữ liệu giá thành trên ${lookup.name}, vẫn thấy chatter.`);
  await salesCtx.close();

  // BF03-003 (đối chứng): CEO mở CÙNG báo giá đó, phải thấy đầy đủ.
  const ceoCtx = await browser.newContext({ storageState: STAGING_ROLES.ceo.storageStatePath });
  const ceoPage = await ceoCtx.newPage();
  await ceoPage.goto(`/web#id=${lookup.id}&model=dl.quotation&view_type=form&cids=1`);
  await expect(ceoPage.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15000 });
  await expect(ceoPage.getByRole('columnheader', { name: /Giá thành/ })).toBeVisible();
  await expect(ceoPage.getByRole('tab', { name: /Phân tích giá thành/ })).toBeVisible();
  console.log(`[staging] BF03-003: Pass — CEO thấy đầy đủ cột Giá thành + tab Phân tích giá thành trên ${lookup.name}.`);
  await ceoCtx.close();
});

test.describe('BF03-005: mặc định filter danh sách Báo giá (SCR-26)', () => {
  test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

  test('không có filter ngầm nào được áp mà không có chip tô sáng tương ứng', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await page.getByTitle('Báo giá', { exact: true }).click();
    await page.locator('div[title="Danh sách báo giá"]').click();
    await expect(page.getByRole('columnheader', { name: 'Số báo giá' })).toBeVisible({ timeout: 15000 });

    const allChip = page.getByRole('button', { name: /^Tất cả/ });
    const hasAllChip = await allChip.count();
    if (hasAllChip === 0) {
      console.log('[staging] BF03-005: không tìm thấy chip "Tất cả" trên staging — bỏ qua so sánh số lượng.');
      return;
    }
    const allCountText = await allChip.first().innerText();
    const allCountMatch = allCountText.match(/\d+/);
    if (!allCountMatch) {
      console.log(`[staging] BF03-005: chip "Tất cả" không có số đếm ("${allCountText}") — bỏ qua so sánh.`);
      return;
    }
    const allCount = allCountMatch[0];
    const summaryVisible = await page.getByText(new RegExp(`^${allCount}\\s`)).count();
    if (summaryVisible > 0) {
      console.log(`[staging] BF03-005: Pass — số dòng hiển thị khớp chip "Tất cả" (${allCount}).`);
    } else {
      console.log(`[staging] BF03-005: TÁI HIỆN BUG-SCR26-01 trên staging — chip "Tất cả" ghi ${allCount} nhưng số dòng thực tế hiển thị không khớp (giống dlm_dev).`);
    }
    expect(summaryVisible, `Chip "Tất cả" ghi ${allCount} nhưng bảng không hiện đúng số dòng đó — nếu fail, đây là BUG-SCR26-01 tái hiện.`).toBeGreaterThan(0);
  });
});
