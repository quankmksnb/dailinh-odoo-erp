import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.truong_kd.storageStatePath });

test.describe('SCR-26 - Danh sách báo giá (role: Trưởng KD) - chỉ đọc', () => {
  test('KHÔNG thấy nút "+ Tạo báo giá"', async ({ page }) => {
    await page.goto('/web#action=295&model=dl.quotation&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Tạo báo giá/ })).toHaveCount(0);
  });
});

// BUG (bug-log.md, Major): Trưởng KD KHÔNG được phép tạo mới Đơn bán hàng theo FDS, nhưng nút
// "+ Thêm đơn bán" vẫn hiện và form tạo mới hoạt động đầy đủ (nút Lưu không bị khóa).
test.describe('SCR-28 - Đơn bán hàng (role: Trưởng KD) [BUG]', () => {
  test.fixme('KHÔNG thấy nút "+ Thêm đơn bán" (theo FDS: đọc+sửa, không tạo mới)', async ({ page }) => {
    await page.goto('/web#action=327&model=dl.sale.order&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Thêm đơn bán/ })).toHaveCount(0);
  });
});

// BUG (bug-log.md, Minor): FDS yêu cầu Trưởng KD có full CRUD trên Nhóm sản phẩm (nút "Mới"),
// nhưng thực tế không có nút tạo mới nào trên toolbar.
test.describe('SCR-21 - Danh mục / Nhóm sản phẩm (role: Trưởng KD) [BUG]', () => {
  test.fixme('có nút "Mới" để tạo nhóm sản phẩm (full CRUD theo FDS)', async ({ page }) => {
    await page.goto('/web#action=289&model=product.category&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible();
  });
});

test.describe('SCR-06 / SCR-07 - RBAC đúng (role: Trưởng KD)', () => {
  test('SCR-06: thấy nút "Vô hiệu hóa KH" trên chi tiết khách hàng', async ({ page }) => {
    await page.goto('/web#action=145&model=res.partner&view_type=kanban&cids=1&menu_id=67');
    await page.getByText('Cong ty CP Dau tu Kim Long').first().click();
    await expect(page.getByRole('button', { name: /Vô hiệu hóa KH/ })).toBeVisible();
  });

  test('SCR-07: KHÔNG thấy nút "+ Thêm NCC" (action chỉ đọc)', async ({ page }) => {
    await page.goto('/web#action=146&model=res.partner&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Thêm NCC/ })).toHaveCount(0);
  });
});

test.describe('Cấu hình (role: Trưởng KD)', () => {
  test('submenu Cấu hình CHỈ có "Cấu hình Báo giá"', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Cấu hình', { exact: true }).click();
    await expect(page.getByTitle('Cấu hình Báo giá')).toBeVisible();
    await expect(page.getByTitle('Quản lý User')).toHaveCount(0);
    await expect(page.getByTitle('Phân quyền')).toHaveCount(0);
  });
});
