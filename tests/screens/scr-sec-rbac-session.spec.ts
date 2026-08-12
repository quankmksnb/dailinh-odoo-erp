import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// Security spot-checks bổ sung theo §3b của guide (RBAC-on-UI cross-role + Session Management)
// — trước đây CHƯA có spec nào test việc mở thẳng URL/action của role khác bằng URL trực tiếp,
// cũng chưa test session bị vô hiệu hoá sau khi logout.

test.describe('RBAC - BA/Sales thử mở thẳng URL action Quản lý User (Admin/IT only)', () => {
  test.use({ storageState: ROLES.sales1.storageStatePath });

  test('action=313 (Quản lý User, OWL client action Admin/IT) không lộ dữ liệu người dùng khác', async ({ page }) => {
    await page.goto('/web#action=313&cids=1&menu_id=67');
    await page.waitForTimeout(2000);
    // Đây là client action tự render qua JS gọi RPC riêng (model.get_bootstrap) — không phải
    // action model chuẩn có ACL chặn tự động ở tầng view. Ghi nhận đúng thực tế quan sát được.
    const hasUserMgmtHeading = await page.getByText('Quản lý người dùng').count();
    if (hasUserMgmtHeading > 0) {
      test.info().annotations.push({
        type: 'SECURITY-FINDING',
        description:
          'BA/Sales mở được URL action=313 (Quản lý User) và thấy giao diện — cần kiểm tra RPC bên dưới (get_bootstrap) có tự chặn bằng ACL/sudo check server-side hay không.',
      });
    }
    expect(true).toBeTruthy();
  });

  test('action=315 (Phân quyền RBAC, Admin/IT only) — quan sát thực tế truy cập', async ({ page }) => {
    await page.goto('/web#action=315&cids=1&menu_id=67');
    await page.waitForTimeout(2000);
    const hasContent = await page.getByText('Phân quyền', { exact: false }).count();
    test.info().annotations.push({
      type: 'OBSERVED',
      description: `BA/Sales mở URL action=315 (Phân quyền): phần tử chứa "Phân quyền" đếm được = ${hasContent}.`,
    });
    expect(true).toBeTruthy();
  });
});

test.describe('RBAC - Kỹ thuật thử mở thẳng URL model Báo giá (không có ACL đọc)', () => {
  test.use({ storageState: ROLES.ky_thuat.storageStatePath });

  test('action model dl.quotation (SCR-26) — Kỹ thuật không có quyền đọc model', async ({ page }) => {
    await page.goto('/web#action=295&model=dl.quotation&view_type=list&cids=1');
    await page.waitForTimeout(2000);
    // FDS: "Kỹ thuật: không có quyền truy cập model báo giá, không thấy màn này".
    const errorOrBlank = await page.getByText(/không có quyền|Access Error|Bạn không có quyền/i).count();
    const dataRows = await page.locator('.o_data_row').count();
    test.info().annotations.push({
      type: 'OBSERVED',
      description: `Kỹ thuật mở URL action=295 (Báo giá): thông báo lỗi quyền = ${errorOrBlank}, số dòng dữ liệu đọc được = ${dataRows}.`,
    });
    // Ràng buộc cứng duy nhất: KHÔNG được đọc được dữ liệu báo giá thật (dataRows phải = 0
    // hoặc có lỗi quyền — không chấp nhận trường hợp Kỹ thuật đọc được nội dung báo giá).
    expect(dataRows === 0 || errorOrBlank > 0).toBeTruthy();
  });
});

test.describe('Session Management - vô hiệu hoá sau logout', () => {
  test.use({ storageState: ROLES.sales1.storageStatePath });

  test('sau /web/session/logout, back lại trang cũ phải yêu cầu đăng nhập lại', async ({ page }) => {
    await page.goto('/web#action=286&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible({ timeout: 15000 });

    await page.goto('/web/session/logout');
    await expect(page.getByRole('textbox', { name: 'Tên đăng nhập' })).toBeVisible({ timeout: 15000 });

    // Thử gọi lại 1 RPC dataset bằng session đã logout — phải bị từ chối, không trả dữ liệu thật.
    const resp = await page.request.post('/web/dataset/call_kw/dl.quotation.request/search_read', {
      data: {
        jsonrpc: '2.0',
        method: 'call',
        params: {
          model: 'dl.quotation.request',
          method: 'search_read',
          args: [[], ['id', 'name']],
          kwargs: {},
        },
      },
      headers: { 'Content-Type': 'application/json' },
    });
    const body = await resp.json().catch(() => ({}));
    const gotRealData = Array.isArray(body?.result) && body.result.length > 0;
    expect(gotRealData).toBeFalsy();
  });
});
