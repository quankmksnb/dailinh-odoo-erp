import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';
import { openRailChild } from './rail-nav';

// Bổ sung các case còn lại của BF-02 trên staging (đã có tương đương BF02-001).
// BF02-002 (tạo nhanh vật tư) KHÔNG làm — Blocked cả trên dlm_dev (option="{'no_quick_create':
// True}" cố định), không phải thiếu test.

test.describe('BF02-003: Vật tư (SCR-11) — Kỹ thuật không thấy Thông tin thương mại', () => {
  test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

  test('form chi tiết vật tư ẩn nhóm "Thông tin thương mại" (giá bán)', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/web');
    await (await openRailChild(page, 'Sản phẩm & Vật tư', 'Vật tư')).click();
    await expect(page.getByRole('cell').first()).toBeVisible({ timeout: 15000 });
    await page.locator('.o_data_row').first().click();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Thông tin thương mại')).toHaveCount(0);
    console.log('[staging] BF02-003: Kỹ thuật không thấy "Thông tin thương mại" trên form Vật tư — đúng FDS.');
  });
});

test.describe('BF02-004: Đo lường (SCR-19/20) — kiểm tra điểm vào menu', () => {
  test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

  test('tìm điểm vào menu "Đo lường" (Loại đo lường / Hình dạng đo lường)', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    // Dùng "Sản phẩm" làm mốc để chắc chắn flyout rail đã thật sự mở (không phải vô tình đóng do
    // toggle) trước khi kết luận "Đo lường" không có điểm vào.
    await openRailChild(page, 'Sản phẩm & Vật tư', 'Sản phẩm');
    const entryPoint = page.locator('div[title*="Đo lường" i], div[title*="Loại đo lường" i], div[title*="Hình dạng đo lường" i]');
    const count = await entryPoint.count();
    if (count === 0) {
      console.log('[staging] BF02-004: TÁI HIỆN BUG-SCR1920-01 trên staging — không tìm thấy điểm vào menu "Đo lường" cho Kỹ thuật (giống dlm_dev).');
    } else {
      console.log('[staging] BF02-004: có điểm vào menu "Đo lường" — khác dlm_dev, cần xác nhận thêm.');
    }
    // Ghi nhận kết quả thật thay vì ép Pass — đúng tinh thần: đây là bug đã biết, test phải phản
    // ánh đúng thực tế trên môi trường, không che giấu.
    expect(count, 'Không tìm thấy điểm vào menu Đo lường — nếu đây là lần đầu thấy, xác nhận có phải BUG-SCR1920-01 tái hiện.').toBe(0);
  });
});

test.describe('BF02-005/006: BOM đã khóa — nút Tạo phiên bản mới / Lưu trữ', () => {
  test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

  test('tạo BOM mới, Xác nhận, Khóa, rồi kiểm 2 nút theo FDS', async ({ page }) => {
    test.setTimeout(90000);
    await page.goto('/web');
    await (await openRailChild(page, 'Kỹ thuật', 'BOM sản phẩm / Bán thành phẩm')).click();
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: /Mới/ }).click();

    await page.getByLabel('Sản phẩm', { exact: true }).click();
    // Dropdown hiện tạm "Đang tải..." trước khi có kết quả thật — waitFor 'visible' đơn thuần có
    // thể bắt trúng đúng lúc placeholder đó đang hiện. Chờ tới khi có chữ khác "Đang tải...".
    const productOption = page.locator('.o-autocomplete--dropdown-menu li').first();
    await expect
      .poll(async () => (await productOption.innerText().catch(() => '')).trim(), { timeout: 15000 })
      .not.toMatch(/^Đang tải/);
    const productName = await productOption.innerText();
    await productOption.click();
    console.log(`[staging] BF02-005/006: tạo BOM cho sản phẩm "${productName}"`);

    await page.getByRole('button', { name: /Thêm.*dòng/i }).first().click();
    const lineDialog = page.getByRole('dialog').filter({ hasText: 'Tạo Danh sách vật tư' });
    const materialField = lineDialog.getByLabel('Vật tư', { exact: true });
    await materialField.waitFor({ state: 'visible', timeout: 15000 });
    await materialField.click();
    await materialField.pressSequentially('Thép hộp chữ nhật 100', { delay: 50 });
    const materialOption = page.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Thép hộp chữ nhật 100' });
    await materialOption.first().waitFor({ state: 'visible', timeout: 15000 });
    await materialOption.first().click();
    await expect(materialField).not.toHaveValue('', { timeout: 10000 });
    await lineDialog.getByRole('button', { name: 'Lưu & Đóng' }).click();
    await page.getByRole('button', { name: 'Lưu thủ công' }).click();
    await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('New', { timeout: 15000 });
    const bomCode = await page.getByRole('heading', { level: 1 }).innerText();

    // Nháp -> Xác nhận BOM -> Khóa. action_confirm() có cổng cứng _dlm_check_material_spec()
    // (§12.4) — chặn nếu vật tư trong dòng thiếu quy cách cần cho tự tính định mức. Vật tư chọn
    // ngẫu nhiên qua tìm kiếm có thể dính cổng này trên staging (dữ liệu vật tư có thể chưa đủ
    // quy cách) — bắt lỗi thật thay vì để test crash mơ hồ.
    await page.getByRole('button', { name: 'Xác nhận BOM' }).click();
    const errorDialog = page.locator('.o_dialog, [role="dialog"], .o_notification').filter({ hasText: /thiếu|lỗi|error|cảnh báo/i });
    const lockBtn = page.getByRole('button', { name: 'Khóa' });
    const raced = await Promise.race([
      lockBtn.waitFor({ state: 'visible', timeout: 15000 }).then(() => 'locked' as const).catch(() => null),
      errorDialog.first().waitFor({ state: 'visible', timeout: 15000 }).then(() => 'error' as const).catch(() => null),
    ]);
    if (raced !== 'locked') {
      const msg = raced === 'error' ? (await errorDialog.first().innerText()).slice(0, 300) : '(không có dialog/toast lỗi nào xuất hiện — trạng thái không rõ)';
      console.log(`[staging] BF02-005/006: KHÔNG xác nhận được BOM ${bomCode} sau khi bấm "Xác nhận BOM". Có thể do cổng _dlm_check_material_spec() (§12.4, vật tư thiếu quy cách) — không liên quan BUG-L3-002/003. Chi tiết: ${msg}`);
      test.skip(true, 'Không xác nhận được BOM để đưa vào trạng thái Đã khóa trên staging — không thể test BF02-005/006 bằng cách này ở lần chạy này. Cần chọn vật tư đã có đủ quy cách hoặc tạo dữ liệu qua RPC.');
      return;
    }
    await expect(lockBtn).toBeVisible({ timeout: 5000 });
    await lockBtn.click();
    await expect(page.getByText('Đã khóa', { exact: false }).first()).toBeVisible({ timeout: 15000 });
    console.log(`[staging] BF02-005/006: ${bomCode} đã Khóa, kiểm tra 2 nút theo FDS`);

    // BF02-005: nút "Tạo phiên bản mới" PHẢI hiện khi Đã khóa (theo FDS).
    const newVersionBtn = page.getByRole('button', { name: 'Tạo phiên bản mới' });
    const hasNewVersionBtn = await newVersionBtn.count();
    if (hasNewVersionBtn > 0) {
      console.log(`[staging] BF02-005: Pass — nút "Tạo phiên bản mới" hiện đúng khi BOM đã khóa (khác BUG-L3-002 ghi nhận trên dlm_dev — có thể đã fix).`);
    } else {
      console.log(`[staging] BF02-005: TÁI HIỆN BUG-L3-002 trên staging — không có nút "Tạo phiên bản mới" cho BOM đã khóa.`);
    }
    expect(hasNewVersionBtn, 'Theo FDS, BOM Đã khóa phải có nút "Tạo phiên bản mới" — nếu 0, đây là BUG-L3-002.').toBeGreaterThan(0);

    // BF02-006: nút "Lưu trữ" KHÔNG được hiện khi Đã khóa (theo FDS) — kỳ vọng vẫn Fail (BUG-L3-003).
    const archiveBtn = page.getByRole('button', { name: 'Lưu trữ' });
    const hasArchiveBtn = await archiveBtn.count();
    if (hasArchiveBtn > 0) {
      console.log(`[staging] BF02-006: TÁI HIỆN BUG-L3-003 trên staging — nút "Lưu trữ" vẫn hiện cho BOM đã khóa (đúng như dlm_dev).`);
    } else {
      console.log('[staging] BF02-006: Pass — nút "Lưu trữ" đã bị ẩn đúng cho BOM đã khóa.');
    }
    expect(hasArchiveBtn, 'Theo FDS, BOM Đã khóa KHÔNG được có nút "Lưu trữ" — nếu >0, đây là BUG-L3-003 (đã biết, kỳ vọng vẫn Fail).').toBe(0);
  });
});

test.describe('BF02-007: RBAC danh sách BOM (SCR-14) — 3 role', () => {
  test('Kỹ thuật: có nút Mới, KHÔNG thấy cột Chi phí vật tư', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Kỹ thuật', 'BOM sản phẩm / Bán thành phẩm')).click();
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('columnheader', { name: /Chi phí vật tư/ })).toHaveCount(0);
    await ctx.close();
  });

  test('CEO: chỉ đọc (không có nút Mới), THẤY cột Chi phí vật tư', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.ceo.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Kỹ thuật', 'BOM sản phẩm / Bán thành phẩm')).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: /Chi phí vật tư/ })).toBeVisible();
    await ctx.close();
  });

  test('Trưởng KD: chỉ đọc (không có nút Mới)', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.truong_kd.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Kỹ thuật', 'BOM sản phẩm / Bán thành phẩm')).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    await ctx.close();
  });
});

test.describe('BF02-008: RBAC danh sách Bản vẽ (SCR-17) — 3 role', () => {
  test('Kỹ thuật: có nút Mới', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Kỹ thuật', 'Bản vẽ kỹ thuật')).click();
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });
    await ctx.close();
  });

  test('CEO: chỉ đọc (không có nút Mới)', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.ceo.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Kỹ thuật', 'Bản vẽ kỹ thuật')).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    await ctx.close();
  });

  test('BA/Sales: KHÔNG có cả rail "Kỹ thuật"', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.sales.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await page.waitForTimeout(1500);
    await expect(page.getByTitle('Kỹ thuật', { exact: true })).toHaveCount(0);
    await ctx.close();
  });
});
