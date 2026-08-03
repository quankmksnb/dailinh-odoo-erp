import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.ky_thuat.storageStatePath });

test.describe('Kỹ thuật - Menu top-level KHÔNG có Khách hàng/Báo giá', () => {
  test('sidebar không có menu "Khách hàng" và "Báo giá"', async ({ page }) => {
    await page.goto('/web');
    await expect(page.getByTitle('Khách hàng')).toHaveCount(0);
    await expect(page.getByTitle('Báo giá', { exact: true })).toHaveCount(0);
  });
});

test.describe('SCR-24 - RFQ cần xử lý (role: Kỹ thuật)', () => {
  test('cột danh sách không có trường tiền, chỉ có tiến độ kỹ thuật', async ({ page }) => {
    await page.goto('/web#action=322&model=dl.quotation.request&view_type=list&cids=1&menu_id=67');
    for (const col of ['Mã yêu cầu', 'Giai đoạn kỹ thuật', 'Tiến độ kỹ thuật', 'Sản phẩm đã xác định', 'Định mức đã xác định']) {
      await expect(page.getByRole('columnheader', { name: new RegExp(col) })).toBeVisible();
    }
  });

  test('mở RFQ đã đóng: không có nút "Mở báo giá"/"Tạo đơn bán hàng" (Kỹ thuật không có quyền Báo giá)', async ({ page }) => {
    await page.goto('/web#action=322&model=dl.quotation.request&view_type=list&cids=1&menu_id=67');
    await page.getByRole('button', { name: 'Tất cả' }).click();
    await page.getByRole('cell', { name: /RFQ-/ }).first().click();
    await expect(page.getByRole('button', { name: /Mở báo giá/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Tạo đơn bán hàng/ })).toHaveCount(0);
  });
});

// BUG (bug-log.md, CRITICAL): Kỹ thuật thấy được menu "Cấu hình Báo giá" và đọc được tab
// "Lợi nhuận & chiết khấu" (markup, giá sàn, ngưỡng chiết khấu) - dữ liệu lẽ ra phải ẩn với
// Kỹ thuật giống như đã ẩn đúng với BA/Sales ở SCR-27. Input bị disabled (không sửa được) nhưng
// vẫn đọc được số liệu - đây vẫn là rò rỉ dữ liệu nhạy cảm.
test.describe('Cấu hình Báo giá - RBAC dữ liệu lợi nhuận/giá sàn [CRITICAL]', () => {
  test.fixme('Kỹ thuật KHÔNG thấy menu "Cấu hình Báo giá"', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Cấu hình', { exact: true }).click();
    await expect(page.getByTitle('Cấu hình Báo giá')).toHaveCount(0);
  });

  test.fixme('Kỹ thuật KHÔNG đọc được tab "Lợi nhuận & chiết khấu" / "Phê duyệt"', async ({ page }) => {
    await page.goto('/web#action=316&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Lợi nhuận & chiết khấu/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Phê duyệt/ })).toHaveCount(0);
  });

  // Đối chứng: tab Hao hụt & thu hồi là nghiệp vụ hợp lệ cho Kỹ thuật, phải PASS.
  test('Kỹ thuật sửa được tab "Hao hụt & thu hồi" (đúng nghiệp vụ)', async ({ page }) => {
    await page.goto('/web#action=316&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Hao hụt & thu hồi/ })).toBeVisible();
  });
});

// BUG (bug-log.md, Minor): footer danh sách Vật tư đếm sai (hiện "2 sản phẩm" thay vì tổng 22).
test.describe('SCR-11 - Danh sách Vật tư (role: Kỹ thuật)', () => {
  test.fixme('dòng đếm cuối bảng khớp tổng số bản ghi thực tế (22)', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Sản phẩm & Vật tư').click();
    await page.getByTitle('Vật tư', { exact: true }).click();
    await expect(page.getByText(/22 sản phẩm/)).toBeVisible();
  });

  test('form chi tiết vật tư ẩn nhóm "Thông tin thương mại" (giá bán)', async ({ page }) => {
    await page.goto('/web');
    await page.getByTitle('Sản phẩm & Vật tư').click();
    await page.getByTitle('Vật tư', { exact: true }).click();
    await page.getByText(/Thep tam CT3/).first().click();
    await expect(page.getByText('Thông tin thương mại')).toHaveCount(0);
    await expect(page.getByText('Hao hụt & thu hồi')).toBeVisible();
  });
});
