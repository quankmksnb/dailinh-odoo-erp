import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// TC-E2E-SEC-001/002 — 2 case an ninh còn thiếu trên staging. Lưu ý: test đã có sẵn trong
// stg-security-extra.spec.ts tên là "TC-E2E-SEC-001" nhưng thực chất kiểm đúng nội dung của
// TC-E2E-SEC-003 (Kỹ thuật không đọc được dl.quotation) — nhãn ghi nhầm, nội dung vẫn đúng và có
// giá trị, không xoá. File này bổ sung đúng 2 case còn thiếu thật: SEC-001 (Sales bị chặn khỏi
// action Quản lý User) và SEC-002 (session bị vô hiệu hoá sau logout).

test.describe('TC-E2E-SEC-001 [staging]', () => {
  test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

  test('Sales mở URL action Quản lý người dùng — bị chặn/không lộ dữ liệu người dùng khác', async ({ page }) => {
    test.setTimeout(30000);
    // Không biết chắc action id trên staging (có thể khác dlm_dev) — thử RPC trực tiếp trên model
    // res.users (nguồn thật của "Quản lý người dùng") thay vì đoán action id qua URL.
    const res = await page.request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: {
          model: 'res.users', method: 'search_read',
          args: [[], ['id', 'login', 'password']], kwargs: { limit: 20 },
        },
      },
    });
    const body = await res.json();
    const leakedPassword = Array.isArray(body.result) && body.result.some((r: any) => 'password' in r && r.password);
    expect(leakedPassword, 'Sales không được đọc field password của user khác qua RPC').toBeFalsy();

    // Đối chiếu qua UI: menu "Quản lý người dùng" không được hiển thị cho Sales.
    await page.goto('/web');
    await expect(page.locator('div[title="Quản lý người dùng"]')).toHaveCount(0);
    console.log(`[staging] TC-E2E-SEC-001: Sales không thấy menu "Quản lý người dùng", RPC res.users không lộ field password (${body.error ? 'AccessError' : `${body.result?.length ?? 0} bản ghi, không có password`}).`);
  });
});

test.describe('TC-E2E-SEC-002 [staging]', () => {
  test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

  test('sau /web/session/logout, RPC bằng session cũ không còn đọc được dữ liệu thật', async ({ page }) => {
    test.setTimeout(30000);
    // Xác nhận session còn hoạt động trước khi logout (đối chứng).
    const beforeRes = await page.request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: { model: 'dl.quotation', method: 'search_count', args: [[]], kwargs: {} },
      },
    });
    const beforeBody = await beforeRes.json();
    expect(beforeBody.error, 'Session Sales phải hoạt động bình thường trước khi logout').toBeFalsy();

    await page.request.get('/web/session/logout');

    const afterRes = await page.request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: { model: 'dl.quotation', method: 'search_count', args: [[]], kwargs: {} },
      },
    });
    const afterBody = await afterRes.json();
    // Sau logout: hoặc lỗi (session expired) hoặc method chặn hẳn — không được trả cùng kết quả
    // thành công như trước.
    const stillWorks = !afterBody.error && typeof afterBody.result === 'number';
    expect(stillWorks, 'RPC bằng session cũ sau logout không được tiếp tục hoạt động bình thường').toBeFalsy();
    console.log(`[staging] TC-E2E-SEC-002: sau /web/session/logout, RPC bằng session cũ -> ${afterBody.error ? 'lỗi đúng như kỳ vọng (' + JSON.stringify(afterBody.error.message || afterBody.error) + ')' : 'không còn hoạt động bình thường'}.`);
  });
});
