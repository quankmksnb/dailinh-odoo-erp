import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF-01 (tiếp nối) — Kỹ thuật mở RFQ-2026-0001 (đã tạo ở stg-bf01-rfq-flow.spec.ts) và kết luận
// dòng gia công. Database staging CHƯA có BOM/vật tư mẫu nào để gắn cho sản phẩm mới ("Cửa sắt
// hộp 40x40, sơn tĩnh điện") — dựng cả bộ vật tư/BOM đầy đủ nằm ngoài phạm vi smoke-test này, nên
// đi theo nhánh A4 (Không khả thi, đã có sẵn pattern ổn định từ dlm_dev
// scr-25-rfq-wizard.spec.ts) để khép luồng RFQ gọn gàng, đúng 1 kết luận kỹ thuật hợp lệ.
test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

test('Kỹ thuật mở RFQ-2026-0001, kết luận Không khả thi (chưa có BOM mẫu phù hợp)', async ({ page }) => {
  test.setTimeout(60000);
  const rfq = await page.request.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: {
        model: 'dl.quotation.request', method: 'search_read',
        args: [[['name', '=', 'RFQ-2026-0001']], ['id']], kwargs: {},
      },
    },
  }).then((r) => r.json()).then((b) => b.result?.[0]);
  expect(rfq).toBeTruthy();

  await page.goto(`/web#id=${rfq.id}&model=dl.quotation.request&view_type=form`);
  await expect(page.getByText('RFQ này chưa được nhận xử lý')).toBeVisible({ timeout: 15000 });
  await page.locator('button[name="action_open_resolve_wizard"]').click();

  await expect(page.getByText('1. Xác định sản phẩm')).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Không khả thi' }).click();
  const reason = 'Chưa có định mức (BOM) mẫu phù hợp trong hệ thống — cần lập BOM riêng cho đơn này trước khi báo giá được.';
  await page.getByRole('textbox', { name: /Nêu rõ lý do/ }).fill(reason);
  await page.getByRole('button', { name: 'Xác nhận không khả thi' }).click();

  await expect(page).toHaveURL(/model=dl\.quotation\.request/);
  await expect(page.getByText('Tất cả dòng đều được kết luận Không khả thi')).toBeVisible({ timeout: 15000 });
});
