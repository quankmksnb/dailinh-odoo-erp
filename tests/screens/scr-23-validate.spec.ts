import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.sales1.storageStatePath });

// BUG (bug-log.md, Major): dialog "Tạo Sản phẩm gia công" của SCR-23 không chặn Số lượng = 0
// (FDS yêu cầu "Số lượng > 0"), trong khi lại bắt buộc nhầm "Mô tả" và "Ảnh/File đính kèm"
// (FDS không yêu cầu 2 trường này là bắt buộc).
test.describe('SCR-23 - Validate dòng Sản phẩm gia công [BUG]', () => {
  test.fixme('Số lượng = 0 phải bị chặn khi lưu (theo FDS: Số lượng > 0)', async ({ page }) => {
    await page.goto('/web#action=323&model=dl.quotation.request&view_type=form&cids=1&menu_id=67');
    await page.getByRole('textbox', { name: 'Khách hàng' }).click();
    await page.getByRole('article').filter({ hasText: 'Cong ty CP Dau tu Kim Long' }).click();

    await page
      .getByRole('table')
      .filter({ hasText: 'Tên sản phẩmNhóm sản phẩmSản' })
      .getByRole('button', { name: 'Thêm một dòng' })
      .click();
    await page.getByRole('textbox', { name: 'Tên sản phẩm' }).fill('Test SL 0 Validate');
    await page.getByRole('textbox', { name: 'Số lượng' }).fill('0');

    const qtyField = page.locator('.modal.d-block .o_field_float');
    await expect(qtyField).toHaveClass(/o_field_invalid/);
  });

  test.fixme('"Mô tả" và "Ảnh/File đính kèm" KHÔNG được bắt buộc (FDS không yêu cầu)', async ({ page }) => {
    await page.goto('/web#action=323&model=dl.quotation.request&view_type=form&cids=1&menu_id=67');
    await page.getByRole('textbox', { name: 'Khách hàng' }).click();
    await page.getByRole('article').filter({ hasText: 'Cong ty CP Dau tu Kim Long' }).click();

    await page
      .getByRole('table')
      .filter({ hasText: 'Tên sản phẩmNhóm sản phẩmSản' })
      .getByRole('button', { name: 'Thêm một dòng' })
      .click();
    await page.getByRole('textbox', { name: 'Tên sản phẩm' }).fill('Test Mo Ta Anh Optional');
    await page.getByRole('textbox', { name: 'Số lượng' }).fill('5');
    await page.getByRole('button', { name: 'Lưu & Đóng' }).click();

    // Kỳ vọng: dialog đóng lại (lưu thành công) vì Mô tả/Ảnh không bắt buộc theo FDS.
    await expect(page.locator('.modal.d-block')).toHaveCount(0);
  });
});
