import { test, expect, request as playwrightRequest } from '@playwright/test';

// §3a HTTP Flow Testing — endpoint /dl_inventory/scrap_banner (K7, controllers/scrap_banner.py).
// Trước đây CHỈ hàm thuần dlm_scrap_banner_html() bên trong được test (L1) — bản thân route
// HTTP (type="json", auth="user") CHƯA từng bị gọi thẳng ở bất kỳ cấp nào. Route này không có
// tham số, không đụng model nào — nhưng auth="user" là biên bảo mật thật cần xác nhận.
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test.describe('HTTP Flow BF-10: /dl_inventory/scrap_banner (JSON-RPC thuần, không browser)', () => {
  test('TC-SYS-BF10-001: gọi route khi CHƯA đăng nhập — không trả về nội dung banner thật', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    const { body } = await rpc(ctx, '/dl_inventory/scrap_banner', {});
    // auth="user" — chưa đăng nhập thì không có session hợp lệ; route phải KHÔNG trả về
    // result.html (bị chặn ở tầng auth trước khi vào tới action), khác hẳn TC-002 bên dưới.
    expect(body.result?.html).toBeFalsy();
    await ctx.dispose();
  });

  test('TC-SYS-BF10-002: đăng nhập Thủ kho rồi gọi route — trả đúng nội dung dải cảnh báo', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    const login = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'thukho@dlm.demo',
      password: 'Demo@2026',
    });
    expect(login.body.result?.uid).toBeTruthy();

    const { res, body } = await rpc(ctx, '/dl_inventory/scrap_banner', {});
    expect(res.ok()).toBeTruthy();
    expect(body.result?.html).toContain('Tiền bán phế liệu không phải lợi nhuận tăng thêm.');
    expect(body.result?.html).not.toContain('data-o-hide-banner');

    await ctx.dispose();
  });
});
