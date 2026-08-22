import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';
import { openRailChild } from './rail-nav';
import fs from 'fs';

// NFR-P01 [staging] — Tải danh sách RFQ (SCR-22). Trước đó chỉ đo trên dev (0.21-0.22s, 1 user).
// Đo lại trên staging qua mạng thật, 1 user (điều kiện PRD 10 user đồng thời đã có số liệu riêng
// qua k6, xem dòng NFR-P01 k6 trong Performance_DLM — test này chỉ đo tải trang qua trình duyệt
// thật, bổ sung cho số liệu k6 chứ không thay thế).
test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

test('NFR-P01 [staging]: tải danh sách RFQ (SCR-22) < 4 giây', async ({ page }) => {
  test.setTimeout(30000);
  await page.goto('/web');
  const t0 = Date.now();
  const rfqLink = await openRailChild(page, 'Báo giá', 'Quản lý RFQ');
  await rfqLink.click();
  await expect(page.locator('.o_breadcrumb, .o_last_breadcrumb_item').first()).toBeVisible({ timeout: 15000 });
  await page.locator('.o_data_row, .o_view_nocontent').first().waitFor({ timeout: 15000 });
  const seconds = (Date.now() - t0) / 1000;
  console.log(`[staging] NFR-P01 RFQ list: ${seconds.toFixed(3)}s (1 user, staging, qua mạng thật)`);
  fs.writeFileSync(
    'tests/reports/perf-results-staging-rfq.json',
    JSON.stringify({ NFR_P01_list_rfq_staging_seconds: seconds }, null, 2),
    'utf-8',
  );
  expect(seconds).toBeLessThan(4);
});
