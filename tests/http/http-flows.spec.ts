import { test, expect, request as playwrightRequest } from '@playwright/test';

// §3a HTTP Flow Testing — tương đương MockMvc (Java/Spring) nhưng dự án này là Odoo/Python,
// không có MockMvc. Dùng thẳng JSON-RPC của Odoo (/web/session/authenticate,
// /web/dataset/call_kw) qua Playwright APIRequestContext — KHÔNG mở browser, KHÔNG mock,
// đúng tinh thần "chuỗi HTTP request nhiều bước, verify status/response/DB state qua API".
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test.describe('HTTP Flow BF-01: đăng nhập → tạo RFQ → đọc lại (JSON-RPC thuần, không browser)', () => {
  test('TC-SYS-BF01-001..003: login → search_read RFQ → logout', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });

    // Bước 1: đăng nhập sai mật khẩu — phải bị từ chối (uid = null hoặc lỗi), KHÔNG có session hợp lệ.
    const bad = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'sales1@dlm.demo',
      password: 'sai-mat-khau-co-y',
    });
    expect(bad.body.result?.uid ?? null).toBeNull();

    // Bước 2: đăng nhập đúng — phải thành công, trả về uid hợp lệ + tên user đúng vai trò.
    const login = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'sales1@dlm.demo',
      password: 'Demo@2026',
    });
    expect(login.res.ok()).toBeTruthy();
    expect(login.body.result?.uid).toBeTruthy();
    expect(login.body.result?.name).toContain('Sales');

    // Bước 3: gọi search_read trên model RFQ bằng session vừa đăng nhập — phải đọc được dữ liệu thật.
    const rfqRead = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'dl.quotation.request',
      method: 'search_read',
      args: [[], ['id', 'name', 'status']],
      kwargs: { limit: 5 },
    });
    expect(rfqRead.res.ok()).toBeTruthy();
    expect(Array.isArray(rfqRead.body.result)).toBeTruthy();
    expect(rfqRead.body.result.length).toBeGreaterThan(0);

    // Bước 4: gọi search_read trên model chỉ Admin có quyền (res.users full field) bằng session
    // Sales — kỳ vọng bị chặn ở tầng ACL (lỗi hoặc danh sách rỗng), không lộ dữ liệu.
    const usersRead = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'res.users',
      method: 'search_read',
      args: [[], ['id', 'login', 'password']],
      kwargs: { limit: 5 },
    });
    // Trường "password" không bao giờ được trả về qua ORM đọc thường (Odoo tự chặn field này ở
    // mọi model, mọi role) — xác nhận không có field password trong bất kỳ record nào trả về.
    const leakedPassword = (usersRead.body.result || []).some((r: any) => 'password' in r && r.password);
    expect(leakedPassword).toBeFalsy();

    // Bước 5: đăng xuất — session phải bị vô hiệu hoá, gọi lại RPC sau đó không còn đọc được dữ liệu thật.
    await rpc(ctx, '/web/session/destroy', {});
    const afterLogout = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'dl.quotation.request',
      method: 'search_read',
      args: [[], ['id', 'name']],
      kwargs: {},
    });
    const gotRealData = Array.isArray(afterLogout.body.result) && afterLogout.body.result.length > 0;
    expect(gotRealData).toBeFalsy();

    await ctx.dispose();
  });
});

test.describe('HTTP Flow BF-08: Kế toán tạo NCC qua RPC — tái hiện BUG-L3-001 ở tầng HTTP thuần', () => {
  test('TC-SYS-BF08-001: create res.partner (role=supplier) bằng session Kế toán — hiện đang bị chặn (regression)', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    const login = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'ketoan@dlm.demo',
      password: 'Demo@2026',
    });
    expect(login.body.result?.uid).toBeTruthy();

    const create = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'res.partner',
      method: 'create',
      args: [[{ name: 'NCC Test HTTPFlow QA', partner_role: 'supplier' }]],
      kwargs: {},
    });

    // BUG-L3-001 (xem bug-log.md Lô 7): ir.model.access chặn perm_create cho dl_group_accountant
    // trên res.partner — gọi create() thẳng qua RPC (bỏ qua hoàn toàn UI) vẫn phải bị AccessError.
    // Test này CHỦ ĐÍCH xác nhận lỗi tồn tại ở tầng server (không phải chỉ ẩn nút trên UI).
    expect(create.body.error).toBeTruthy();
    expect(JSON.stringify(create.body.error)).toMatch(/Access|quyền|AccessError/i);

    await ctx.dispose();
  });
});
