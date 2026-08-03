import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.admin.storageStatePath });

test.describe('SCR-03 - Quản lý người dùng [PASS]', () => {
  test('Không thể tự khóa tài khoản đang đăng nhập', async ({ page }) => {
    await page.goto('/web#action=313&cids=1&menu_id=67');
    await page.getByRole('row', { name: 'Q QA Admin/IT admin@dlm.demo' }).click();
    await page.getByRole('button', { name: ' Khóa tài khoản' }).click();

    await expect(page.getByText('Không thể khóa')).toBeVisible();
    await expect(page.getByText('Bạn không thể tự khóa tài khoản đang đăng nhập.')).toBeVisible();
    await page.getByRole('button', { name: 'Đã hiểu' }).click();

    await expect(
      page.getByRole('row', { name: 'Q QA Admin/IT admin@dlm.demo' }).getByText('Hoạt động'),
    ).toBeVisible();
  });

  test('Chặn tạo user với email/login đã tồn tại', async ({ page }) => {
    await page.goto('/web#action=313&cids=1&menu_id=67');
    await page.getByRole('button', { name: ' Tạo người dùng' }).click();
    await page.getByRole('textbox', { name: 'Nguyễn Văn A' }).fill('QA Duplicate Email Test');
    await page.getByRole('textbox', { name: 'user@dailinh.vn' }).fill('sales1@dlm.demo');
    await page.getByRole('button', { name: 'Lưu & gửi lời mời' }).click();

    await expect(page.getByText('Không thực hiện được')).toBeVisible();
    await expect(page.getByText("'sales1@dlm.demo' đã tồn tại")).toBeVisible();
  });
});

// BUG (bug-log.md, Critical): tick/untick CRUD trong SCR-04 báo AccessError vì dl_group_admin
// thiếu base.group_system — chặn hoàn toàn màn Phân quyền cho chính Admin/IT.
test.describe('SCR-04 - Phân quyền RBAC [BUG - Critical]', () => {
  test.fixme(
    'Tick checkbox Xem cho "Quản lý người dùng" phải lưu được, không báo AccessError',
    async ({ page }) => {
      await page.goto('/web#action=315&cids=1&menu_id=67');
      await page.getByText('Admin/IT', { exact: true }).first().click();

      const row = page.getByRole('row', { name: 'Quản lý người dùng' });
      await row.locator('td').nth(1).locator('.dl-rperm-check').click();

      await expect(page.getByText('Không thực hiện được')).toHaveCount(0);
      await expect(row.locator('td').nth(1).locator('checkbox')).toBeChecked();
    },
  );
});
