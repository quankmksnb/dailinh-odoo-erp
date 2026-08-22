import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-05 Send Quotation to Customer — trước đây "Not Run", chưa từng bấm nút Gửi khách hàng thật.
// Đã xác nhận thủ công qua Playwright MCP với BG/2026/0018 (id=18) — chuyển Đã duyệt nội bộ →
// Đã gửi khách, sinh PDF đính kèm tự động, set Hạn hiệu lực. Test tự động dưới đây dùng báo giá
// demo còn lại ở trạng thái Đã duyệt nội bộ (BG/2026/0027, id=28) vì id=18 đã bị mutate không
// idempotent bởi lần xác nhận thủ công.
test.use({ storageState: ROLES.sales1.storageStatePath });

test('BF-05: Sales bấm "Gửi khách hàng" trên báo giá Đã duyệt nội bộ → Đã gửi khách + sinh PDF', async ({ page }) => {
  await page.goto('/web#action=295&model=dl.quotation&view_type=form&id=28&cids=1');
  await expect(page.getByText('Đã được phê duyệt')).toBeVisible({ timeout: 15000 });

  const directBtn = page.getByRole('button', { name: 'Gửi khách hàng', exact: true });
  if (await directBtn.count()) {
    await directBtn.click();
  } else {
    await page.getByRole('button', { name: 'Tác vụ' }).click();
    await page.getByRole('button', { name: 'Gửi khách hàng' }).click();
  }

  // Trạng thái chuyển Đã gửi khách (bước 3 trong statusbar được tick), sinh PDF đính kèm.
  await expect(page.getByText('Đã phát hành báo giá')).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Bao_gia_BG_2026_0027\.pdf/)).toBeVisible();
});
