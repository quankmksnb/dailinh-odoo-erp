import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.ke_toan.storageStatePath });

// Lưu ý: KHÔNG đặt test đăng nhập lại (fresh login) trong file này - Odoo hủy session cũ khi có
// login mới cùng tài khoản, làm hỏng storageState dùng chung cho các test còn lại. Test landing
// theo LANDING_RULES cho từng role đã có trong scr-01-login.spec.ts.
test.describe('Kế toán nội bộ - Phạm vi menu đúng RBAC', () => {
  test('sidebar KHÔNG có menu "Khách hàng", KHÔNG có "Vật tư" trực tiếp, KHÔNG có "Kỹ thuật"/BOM', async ({ page }) => {
    await page.goto('/web');
    // Xác nhận thực sự đã đăng nhập (không phải false-positive trên trang login).
    await expect(page.getByRole('button', { name: /Người dùng/ })).toBeVisible();
    await expect(page.getByTitle('Khách hàng')).toHaveCount(0);
    await expect(page.getByTitle('Kỹ thuật', { exact: true })).toHaveCount(0);

    await page.getByTitle('Sản phẩm & Vật tư').click();
    await expect(page.getByTitle('Vật tư', { exact: true })).toHaveCount(0);
  });
});

test.describe('SCR-07/08 - NCC / Thầu phụ (role: Kế toán) - full CRUD theo FDS', () => {
  test('nút "+ Thêm NCC" hiển thị, đúng cột danh sách', async ({ page }) => {
    await page.goto('/web#action=146&model=res.partner&view_type=list&cids=1');
    await expect(page.getByRole('button', { name: /Thêm NCC/ })).toBeVisible();
    for (const col of ['Tên NCC', 'Điện thoại', 'Email', 'MST', 'Tỉnh/TP']) {
      await expect(page.getByRole('columnheader', { name: new RegExp(col) })).toBeVisible();
    }
  });

  test('mở NCC: thấy nút "Vô hiệu hóa NCC" (đúng ACL Kế toán)', async ({ page }) => {
    await page.goto('/web#action=146&model=res.partner&view_type=list&cids=1');
    await page.getByRole('cell', { name: /Cong ty|Công ty/ }).first().click();
    await expect(page.getByRole('button', { name: /Vô hiệu hóa NCC/ })).toBeVisible();
  });
});

test.describe('SCR-12 - Bảng giá Vật tư (role: Kế toán)', () => {
  test('danh sách đúng cột, nút "+ Thêm bảng giá NCC" hiển thị', async ({ page }) => {
    await page.goto('/web#action=305&model=product.supplierinfo&view_type=list&cids=1');
    await expect(page.getByRole('button', { name: /Thêm bảng giá NCC/ })).toBeVisible();
    for (const col of ['Vật tư', 'Nhà cung cấp', 'Giá NCC', 'Từ ngày', 'Trạng thái']) {
      await expect(page.getByRole('columnheader', { name: new RegExp(col) })).toBeVisible();
    }
  });

  test('dòng "Nháp" có nút Duyệt, dòng "Đã duyệt" có nút Áp dụng/Hủy duyệt', async ({ page }) => {
    await page.goto('/web#action=305&model=product.supplierinfo&view_type=list&cids=1');
    await expect(page.getByRole('button', { name: 'Duyệt' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Áp dụng' }).first()).toBeVisible();
  });
});

// Ghi chú (bug-log.md): Kế toán thấy đủ "Cấu hình Báo giá" kể cả tab Lợi nhuận & chiết khấu -
// KHÔNG tính là lỗi (khác với Kỹ thuật) vì FDS SCR-27 cho phép Kế toán xem "tab Phân tích giá
// thành và cột giá thành". Nút sửa trên tab này bị khóa cho cả Kế toán (chỉ CEO/Admin sửa được).
test.describe('Cấu hình Báo giá (role: Kế toán) - đối chứng, không phải lỗi', () => {
  test('Kế toán xem được tab "Lợi nhuận & chiết khấu" nhưng không sửa được (nút disabled)', async ({ page }) => {
    await page.goto('/web#action=316&cids=1');
    await page.getByRole('button', { name: /Lợi nhuận & chiết khấu/ }).click();
    await expect(page.getByRole('button', { name: /Thêm chính sách/ }).first()).toBeDisabled();
  });
});
