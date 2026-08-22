import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';
import { openRailChild } from './rail-nav';

// TC-E2E-BF10-009 [staging] — code cho thấy chỉ view_dl_scrap_quant_tree (SCR-42, danh sách
// Phế liệu) có banner_route; view_dl_scrap_sale_form (form Bán phế liệu, có thể là SCR-43) không
// có banner_route ở đâu cả trong scrap_views.xml. Kiểm tra cả 2 màn thật trên server.
test.use({ storageState: STAGING_ROLES.thu_kho.storageStatePath });

test('TC-E2E-BF10-009 [staging]: kiểm tra banner trên cả danh sách Phế liệu và form Bán phế liệu', async ({ page }) => {
  test.setTimeout(30000);
  await page.goto('/web');
  const link = await openRailChild(page, 'Kho', 'Phế liệu');
  await link.click();
  await expect(page.locator('.o_breadcrumb, .o_last_breadcrumb_item').first()).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(1000);

  const bannerOnList = await page.getByText(/không phải lợi nhuận tăng thêm/i).count();
  console.log(`[staging] TC-E2E-BF10-009: banner trên danh sách Phế liệu (SCR-42) = ${bannerOnList > 0}`);

  const saleBtn = page.getByRole('button', { name: /Bán phế liệu/ });
  const hasSaleBtn = await saleBtn.count();
  console.log(`[staging] TC-E2E-BF10-009: có nút "Bán phế liệu" = ${hasSaleBtn > 0}`);
  if (hasSaleBtn > 0) {
    await saleBtn.first().click();
    await page.waitForTimeout(1500);
    const bannerOnForm = await page.getByText(/không phải lợi nhuận tăng thêm/i).count();
    console.log(`[staging] TC-E2E-BF10-009: banner trên form Bán phế liệu (SCR-43?) = ${bannerOnForm > 0}`);
  }
  await page.screenshot({ path: 'tests/reports/evidence/bf10-009-recheck.png' });
});
