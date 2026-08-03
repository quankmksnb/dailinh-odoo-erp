import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.describe('SCR-01 - Đăng nhập (role: BA/Sales)', () => {
  test('đăng nhập đúng tài khoản → vào được backend', async ({ page }) => {
    await page.goto('/web/login');
    await page.getByRole('textbox', { name: 'Tên đăng nhập' }).fill(ROLES.sales1.login);
    await page.getByRole('textbox', { name: 'Mật khẩu' }).fill(ROLES.sales1.password);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();

    await expect(page.getByRole('button', { name: /Người dùng/ })).toBeVisible();
  });

  // ĐÍNH CHÍNH (bug-log.md): FDS SCR-01 ghi "Đăng nhập thành công → Home Hub (SCR-35) fullscreen",
  // nhưng đọc source `dl_base/home.js` xác nhận đây là hành vi CHỦ ĐÍCH đã đổi: mỗi role landing
  // thẳng vào 1 action nghiệp vụ riêng (LANDING_RULES), Home Hub dạng lưới thẻ không còn hiển thị
  // cho role nào. Đây là xung đột FDS/Code cần BA xác nhận cập nhật tài liệu, KHÔNG phải bug -
  // test dưới đây xác nhận đúng hành vi landing hiện tại của code (PASS), không phải test bug.
  test('đăng nhập thành công → landing đúng theo LANDING_RULES của role (Báo giá cho BA/Sales)', async ({ page }) => {
    await page.goto('/web/login');
    await page.getByRole('textbox', { name: 'Tên đăng nhập' }).fill(ROLES.sales1.login);
    await page.getByRole('textbox', { name: 'Mật khẩu' }).fill(ROLES.sales1.password);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();

    await expect(page).toHaveURL(/action=295&model=dl\.quotation/);
  });

  // ĐÍNH CHÍNH: logo "Trang chủ" hoạt động đúng - nó mở lại Home Hub, Home Hub tự động redirect
  // về action landing của role. Test trước đây tưởng nhầm là "không làm gì" vì test lúc đã đứng
  // sẵn ở đúng màn landing. Test dưới đây điều hướng sang màn khác trước, rồi bấm logo, xác nhận
  // nó bật lại đúng màn landing (Báo giá) - không phải dead-link.
  test('click logo "Trang chủ" → quay lại đúng màn landing của role', async ({ page }) => {
    await page.goto('/web/login');
    await page.getByRole('textbox', { name: 'Tên đăng nhập' }).fill(ROLES.sales1.login);
    await page.getByRole('textbox', { name: 'Mật khẩu' }).fill(ROLES.sales1.password);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();
    await expect(page.getByRole('button', { name: /Người dùng/ })).toBeVisible();

    // Điều hướng sang màn khác (Khách hàng) trước khi test logo, để tránh false-negative
    // khi đang đứng sẵn ở đúng màn landing.
    await page.getByTitle('Khách hàng').click();
    await expect(page).toHaveURL(/model=res\.partner/);

    await page.getByText('◆DLM-ERP').click();
    await expect(page).toHaveURL(/action=295&model=dl\.quotation/);
  });
});
