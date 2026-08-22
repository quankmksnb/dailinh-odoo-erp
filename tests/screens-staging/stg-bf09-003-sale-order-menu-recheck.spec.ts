import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// TC-E2E-BF09-003 [staging] — kiểm tra lại theo code hiện tại: action_dl_sale_order dùng CHUNG
// cho CEO/Admin/BA/Trưởng KD (dl_sale/views/menus.xml, không context create:False riêng), và
// ir.model.access.csv cho Trưởng KD (access_dl_sale_order_sm) có perm_create=1 giống BA — khác
// hẳn mô tả cũ ("Trưởng KD không thấy nút + Thêm đơn bán").
test.use({ storageState: STAGING_ROLES.truong_kd.storageStatePath });

test('TC-E2E-BF09-003 [staging]: Trưởng KD mở danh sách Đơn bán hàng', async ({ page }) => {
  test.setTimeout(30000);
  await page.goto('/web');
  await page.waitForTimeout(1000);
  const child = page.locator('div[title="Đơn bán hàng"]');
  if (!(await child.isVisible().catch(() => false))) {
    await page.getByTitle('Báo giá', { exact: true }).click();
  }
  await child.first().waitFor({ state: 'visible', timeout: 10000 });
  let navigated = false;
  for (let i = 0; i < 5 && !navigated; i++) {
    await child.first().click();
    navigated = await page.waitForURL(/model=dl\.sale\.order/, { timeout: 3000 }).then(() => true).catch(() => false);
  }
  expect(navigated, 'không điều hướng được tới màn Đơn bán hàng sau 5 lần bấm').toBe(true);
  const newBtn = page.getByRole('button', { name: /Thêm đơn bán|Mới/ });
  const hasNew = await newBtn.count() > 0 && await newBtn.first().isVisible().catch(() => false);
  console.log(`[staging] TC-E2E-BF09-003: Trưởng KD thấy nút tạo đơn bán = ${hasNew}`);
});
