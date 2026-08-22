import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.sales1.storageStatePath });

test.describe('SCR-28 - Danh sách Đơn bán hàng (role: BA/Sales)', () => {
  test('nút "+ Thêm đơn bán" hiển thị, đúng cột theo FDS', async ({ page }) => {
    await page.goto('/web#action=327&model=dl.sale.order&view_type=list&cids=1');
    await expect(page.getByRole('button', { name: /Thêm đơn bán/ })).toBeVisible();
    for (const col of ['Số đơn', 'Khách hàng', 'Báo giá', 'Ngày', 'Tổng tiền', 'Trạng thái']) {
      await expect(page.getByRole('columnheader', { name: new RegExp(col) })).toBeVisible();
    }
  });
});
