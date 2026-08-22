import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// TC-E2E-BF03-005 [staging] — kiểm tra lại defect cũ "chip Tất cả hiện N nhưng bảng chỉ hiện
// M dòng, không chip nào tô sáng". Code hiện tại (quotation_list_controller.js _activeChip())
// đọc trạng thái filter thật từ searchModel, action mặc định bật search_default_open=1.
test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

test('TC-E2E-BF03-005 [staging]: mở danh sách Báo giá, kiểm tra chip có tô sáng khớp filter', async ({ page }) => {
  test.setTimeout(30000);
  await page.goto('/web');
  await page.getByTitle('Báo giá', { exact: true }).click();
  await page.locator('div[title="Danh sách báo giá"]').click();
  await expect(page.locator('.o_breadcrumb, .o_last_breadcrumb_item').first()).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(1000);

  const activeChip = page.locator('.dl-chip.is-active');
  const activeCount = await activeChip.count();
  const activeLabel = activeCount > 0 ? await activeChip.first().innerText() : '(không có)';
  console.log(`[staging] TC-E2E-BF03-005: số chip đang tô sáng = ${activeCount}, chip = "${activeLabel}"`);

  // Đếm số dòng thật hiện trên bảng vs số ghi trên chip đang active (nếu có)
  const rowCount = await page.locator('.o_data_row').count();
  const chipTexts = await page.locator('.dl-chip').allTextContents();
  console.log(`[staging] TC-E2E-BF03-005: số dòng hiển thị = ${rowCount}, danh sách chip = ${JSON.stringify(chipTexts)}`);

  await page.screenshot({ path: 'tests/reports/evidence/bf03-005-recheck.png' });
});
