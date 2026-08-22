import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';
import { openRailChild } from './rail-nav';

test.describe('BF09-003 (RBAC): Trưởng KD mở danh sách Đơn bán hàng (SCR-28)', () => {
  test.use({ storageState: STAGING_ROLES.truong_kd.storageStatePath });

  test('KHÔNG thấy nút "+ Thêm đơn bán" (theo FDS: đọc + sửa, không tạo mới)', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await (await openRailChild(page, 'Báo giá', 'Đơn bán hàng')).click();
    await page.waitForTimeout(1500);
    const addBtn = page.getByRole('button', { name: /Thêm đơn bán/i });
    const count = await addBtn.count();
    if (count > 0) {
      console.log('[staging] BF09-003: TÁI HIỆN BUG-SCR28-01 trên staging — nút "+ Thêm đơn bán" vẫn hiện cho Trưởng KD, giống dlm_dev.');
    } else {
      console.log('[staging] BF09-003: Pass — Trưởng KD không thấy nút "+ Thêm đơn bán".');
    }
    expect(count, 'Theo FDS, Trưởng KD chỉ đọc + sửa, không được tạo Đơn bán hàng mới — nếu >0, đây là BUG-SCR28-01 tái hiện.').toBe(0);
  });
});

test.describe('BF09-004 (RBAC): Danh sách Sản phẩm (SCR-09) — 3 role', () => {
  // GHI CHÚ: Report 5.3 (BF09-004 gốc) ghi "BA/Sales có nút Mới" — nhưng code hiện tại
  // (dl_product/views/menus.xml, menu_dl_product_view) gán CÙNG 1 action view-only cho cả CEO lẫn
  // BA/Sales, với comment tường minh "View-only: CEO, Sales/BA" — đây là thiết kế chủ đích đã đổi
  // sau khi Report 5.3 được viết, không phải bug. Test dưới đây phản ánh đúng hành vi HIỆN TẠI.
  test('BA/Sales: KHÔNG có nút "Mới" (view-only theo code hiện tại — khác mô tả cũ trong Report 5.3)', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.sales.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Sản phẩm & Vật tư', 'Sản phẩm')).click();
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    console.log('[staging] BF09-004: xác nhận Sales không có nút "Mới" trên Sản phẩm — khớp code hiện tại (view-only), Report 5.3 cần cập nhật lại mô tả cũ.');
    await ctx.close();
  });

  test('CEO: KHÔNG có nút "Mới"', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.ceo.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Sản phẩm & Vật tư', 'Sản phẩm')).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    await ctx.close();
  });

  test('Trưởng KD: KHÔNG có nút "Mới"', async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES.truong_kd.storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await (await openRailChild(page, 'Sản phẩm & Vật tư', 'Sản phẩm')).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    await ctx.close();
  });
});
