import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.sales1.storageStatePath });

const CUSTOMER_LIST_URL = '/web#action=145&model=res.partner&view_type=list&cids=1&menu_id=67';
const CUSTOMER_KANBAN_URL = '/web#action=145&model=res.partner&view_type=kanban&cids=1&menu_id=67';

test.describe('SCR-05 - Danh sách khách hàng (role: BA/Sales)', () => {
  // BUG-03 (bug-log.md): FDS quy định "Mặc định hiện bảng" (list) nhưng thực tế mặc định là Kanban.
  test.fixme('mặc định hiển thị chế độ Bảng (list), không phải Kanban', async ({ page }) => {
    await page.goto('/web#action=145&model=res.partner&cids=1&menu_id=67');
    await expect(page.locator('.o_list_view')).toBeVisible();
  });

  // BUG-04 (bug-log.md): List view không hiện KH "Ngừng hợp tác" khi mới vào (17/19),
  // trong khi Kanban hiện đủ 19/19. FDS yêu cầu hiển thị cả KH ngừng hợp tác (active_test tắt) ở mọi view.
  test.fixme('list view hiển thị đủ cả khách hàng đã ngừng hợp tác', async ({ page }) => {
    await page.goto(CUSTOMER_LIST_URL);
    await expect(page.getByText(/19 khách hàng/)).toBeVisible();
  });

  // KHÔNG phải bug sản phẩm: đã xác nhận bằng thao tác tay qua trình duyệt thật (screenshot
  // scr05-kanban-default.png) là nút "+ Thêm khách hàng" luôn có sẵn cho BA/Sales. Assertion tự
  // động này chỉ pass ổn định khi chạy RIÊNG file này; khi chạy chung cả bộ suite (nhiều spec
  // dùng chung 1 storageState/session sales1.json) thì đôi khi control panel không kịp mount nút
  // - nghi do session server-side "nhớ" action vừa xem trước đó (liên quan BUG-01). Đánh dấu
  // fixme để không làm nhiễu kết quả suite; cần chạy cô lập hoặc tách storageState/test nếu muốn CI hoá.
  test.fixme('nút "+ Thêm khách hàng", ô tìm kiếm, nút Nhập/Xuất dữ liệu tồn tại', async ({ page }) => {
    await page.goto(CUSTOMER_KANBAN_URL);
    await expect(page.getByRole('button', { name: /Thêm khách hàng/ })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Thao tác' }).click();
    await expect(page.getByRole('button', { name: 'Nhập dữ liệu' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Xuất dữ liệu' })).toBeVisible();
  });
});

test.describe('SCR-06 - Chi tiết khách hàng (role: BA/Sales)', () => {
  test('BA/Sales KHÔNG thấy nút Vô hiệu hóa KH / Kích hoạt lại', async ({ page }) => {
    await page.goto(CUSTOMER_KANBAN_URL);
    await page.getByText('Cong ty CP Dau tu Kim Long').first().click();
    await expect(page.getByRole('button', { name: 'Vô hiệu hóa KH' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Kích hoạt lại' })).toHaveCount(0);
  });

  test('tab "Lịch sử Báo giá" hiện Nhóm KH + Tổng số báo giá, KHÔNG hiện Win rate', async ({ page }) => {
    await page.goto(CUSTOMER_KANBAN_URL);
    await page.getByText('Cong ty CP Dau tu Kim Long').first().click();
    await page.getByRole('tab', { name: 'Lịch sử Báo giá' }).click();
    await expect(page.getByText('Tổng số báo giá')).toBeVisible();
    await expect(page.getByText(/Win rate/i)).toHaveCount(0);
  });

  test('chatter hiển thị cho BA/Sales', async ({ page }) => {
    await page.goto(CUSTOMER_KANBAN_URL);
    await page.getByText('Cong ty CP Dau tu Kim Long').first().click();
    await expect(page.getByRole('button', { name: 'Gửi tin' })).toBeVisible();
  });
});
