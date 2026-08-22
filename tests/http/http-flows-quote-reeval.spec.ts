import { test, expect, request as playwrightRequest } from '@playwright/test';

// §3a HTTP Flow — TC-SYS-BF03-001 (đánh giá lại điều kiện phê duyệt qua RPC thuần).
//
// TC-E2E-BF03-004 (sheet E2E_BF_DLM_Playwright) không thể dựng bằng browser: field
// discount_pct trên form Báo giá bị khoá readonly="state != 'draft'" (quotation_views.xml
// dòng 221) — ngoài Nháp, Sales KHÔNG có cách nào sửa Chiết khấu qua UI. Đúng như chính
// docstring của _reevaluate_approval() trong dl_quotation.py: "Tình huống này chỉ xảy ra
// khi ghi thẳng qua RPC — trên form các field đó đã khoá ngoài Nháp." Nên kịch bản này chỉ
// kiểm được ở tầng §3a (JSON-RPC thuần, bỏ qua UI), không phải §3b — đặt test ở đây thay vì
// tests/screens/.
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test.describe('HTTP Flow BF-03: sửa Chiết khấu qua RPC trên báo giá "Đã gửi khách" -> tự quay về Nháp', () => {
  test('TC-SYS-BF03-001: write(discount_pct vượt max) qua RPC -> state tự chuyển draft', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    const login = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'sales1@dlm.demo',
      password: 'Demo@2026',
    });
    expect(login.body.result?.uid).toBeTruthy();

    // Tìm ĐỘNG 1 báo giá đang "Đã gửi khách" với Chiết khấu còn dưới mức tối đa — không chốt
    // cứng 1 tên bản ghi, vì chạy lại nhiều lần sẽ tự kéo bản ghi vừa dùng về Nháp (không còn
    // "sent" nữa), cần chọn được bản ghi khác ở lần chạy sau.
    const before = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'dl.quotation',
      method: 'search_read',
      args: [[['state', '=', 'sent']], ['id', 'name', 'state', 'discount_pct', 'discount_max_rate']],
      kwargs: { limit: 20 },
    });
    const quote = (before.body.result || []).find(
      (q: any) => q.discount_pct < q.discount_max_rate
    );
    expect(quote, 'cần ít nhất 1 báo giá "Đã gửi khách" với Chiết khấu dưới mức tối đa trong seed data').toBeTruthy();

    // Ghi thẳng discount_pct vượt discount_max_rate qua RPC (bỏ qua UI hoàn toàn).
    const write = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'dl.quotation',
      method: 'write',
      args: [[quote.id], { discount_pct: quote.discount_max_rate + 10 }],
      kwargs: {},
    });
    expect(write.body.error).toBeFalsy();

    const after = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'dl.quotation',
      method: 'search_read',
      args: [[['id', '=', quote.id]], ['id', 'state']],
      kwargs: {},
    });
    // _reevaluate_approval(): vượt ngưỡng trong khi đang 'sent' -> tự kéo về 'draft'.
    expect(after.body.result?.[0]?.state).toBe('draft');

    await ctx.dispose();
  });
});
