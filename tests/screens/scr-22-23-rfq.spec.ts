import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.sales1.storageStatePath });

test.describe('SCR-23 - Tạo RFQ (giao diện Sales)', () => {
  test('form "Tạo RFQ" tách 2 bảng Thương mại / Gia công, không có cột kỹ thuật', async ({ page }) => {
    await page.goto('/web#action=323&model=dl.quotation.request&view_type=form&cids=1');
    await expect(page.getByText('Sản phẩm thương mại')).toBeVisible();
    await expect(page.getByText('Sản phẩm gia công')).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Sản phẩm đã xác định' })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: 'BOM' })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: 'Không khả thi' })).toHaveCount(0);
  });
});

test.describe('SCR-22 - Danh sách RFQ / SCR-24 form khi mở từ danh sách', () => {
  // BUG-05 (bug-log.md): Mở 1 RFQ có sẵn từ menu "Quản lý RFQ" hiển thị form gộp 1 bảng
  // (kiểu Kỹ thuật - SCR-24, có cột "Sản phẩm đã xác định"/"Không khả thi") thay vì form Sales
  // tách 2 bảng như khi bấm "Tạo RFQ". FDS SCR-23 ghi "Không có cột Sản phẩm xác định/BOM/Không khả thi".
  test.fixme(
    'mở RFQ có sẵn từ "Quản lý RFQ" vẫn dùng form Sales (tách 2 bảng), không lộ cột kỹ thuật',
    async ({ page }) => {
      await page.goto('/web#action=321&model=dl.quotation.request&view_type=list&cids=1');
      await page.getByRole('button', { name: 'Tất cả' }).click();
      await page.getByRole('cell', { name: /RFQ-/ }).first().click();
      await expect(page.getByRole('columnheader', { name: 'Sản phẩm đã xác định' })).toHaveCount(0);
      await expect(page.getByRole('columnheader', { name: 'Không khả thi' })).toHaveCount(0);
    }
  );

  test('field "Không khả thi" (nếu hiện) bị khóa read-only với BA/Sales', async ({ page }) => {
    await page.goto('/web#action=321&model=dl.quotation.request&view_type=list&cids=1');
    await page.getByRole('button', { name: 'Tất cả' }).click();
    await page.getByRole('cell', { name: /RFQ-/ }).first().click();
    const checkbox = page.getByRole('cell', { name: 'Không khả thi' }).locator('input[type="checkbox"]');
    if (await checkbox.count()) {
      await expect(checkbox).toBeDisabled();
    }
  });
});
