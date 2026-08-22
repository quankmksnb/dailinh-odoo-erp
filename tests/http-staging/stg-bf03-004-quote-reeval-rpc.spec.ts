import { test, expect, request as playwrightRequest } from '@playwright/test';

// TC-E2E-BF03-004 (sheet E2E_BF_DLM_Playwright) — Actor "System": sau khi lưu báo giá, hệ thống
// tự đánh giá theo ma trận phê duyệt. Test ở tầng RPC thuần (giống cách case này đã được test
// trước đó theo Evidence cũ "RPC trực tiếp trên server"), không qua UI — vì đây là hành vi
// System, không phải thao tác của 1 actor cụ thể trên màn hình.
//
// Xác nhận đúng 2 vế đã ghi trong Notes: (1) báo giá giá trị nhỏ (dưới ngưỡng) tạo xong
// approval_state=not_required ngay; (2) báo giá giá trị lớn (vượt ngưỡng 20.000.001đ) VẪN
// not_required ngay sau create() — dl_quotation.py's create() không gọi reevaluate_quotation(),
// chỉ write() với field trong _REEVAL_TRIGGER_FIELDS mới kích hoạt — cho tới lần write() đầu
// tiên mới tự chuyển "Chờ phê duyệt". Đây là gap thật đã ghi nhận (không phải lỗi test) — xem
// cùng phát hiện ở tests/screens-staging/stg-bf04-approval-flow.spec.ts (kiểm ở tầng UI).
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

async function rpc(ctx: any, model: string, method: string, args: unknown[], kwargs: Record<string, unknown> = {}) {
  const res = await ctx.post('/web/dataset/call_kw', {
    data: { jsonrpc: '2.0', method: 'call', params: { model, method, args, kwargs } },
  });
  return res.json();
}
async function rpcOk(ctx: any, model: string, method: string, args: unknown[], kwargs: Record<string, unknown> = {}) {
  const body = await rpc(ctx, model, method, args, kwargs);
  if (body.error) throw new Error(`RPC ${model}.${method} lỗi: ${JSON.stringify(body.error.data?.message || body.error)}`);
  return body.result;
}

test('TC-E2E-BF03-004 [staging RPC]: create() không tự đánh giá lại; write() mới kích hoạt phê duyệt', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await (await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'ba@gmail.com', password: PASSWORD } },
  })).json();
  if (!auth.result?.uid) throw new Error('Đăng nhập thất bại');

  const partner = (await rpcOk(ctx, 'res.partner', 'search_read',
    [[['name', 'like', 'Việt Thành']]], { fields: ['id'], limit: 1 }))[0];
  if (!partner) throw new Error('Không tìm thấy khách hàng test "Việt Thành" — cần chạy trước 1 pilot BF-01 để có dữ liệu.');

  // Vế 1: báo giá nhỏ, dưới ngưỡng 20.000.001đ — phải not_required ngay sau create().
  const smallId = await rpcOk(ctx, 'dl.quotation', 'create', [{
    partner_id: partner.id,
    line_ids: [[0, 0, { name: 'Bản lề thép 6 phân', qty: 1, price_unit: 100000 }]],
  }]);
  const small = (await rpcOk(ctx, 'dl.quotation', 'read', [[smallId], ['approval_state', 'approval_required']]))[0];
  console.log(`[staging] BF03-004 vế 1: báo giá nhỏ id=${smallId}, approval_state=${small.approval_state}`);
  expect(small.approval_state, 'báo giá dưới ngưỡng phải not_required ngay sau create()').toBe('not_required');

  // Vế 2: báo giá lớn, vượt ngưỡng 20.000.001đ (30 x 850.000 = 25.500.000đ, giống stg-bf04-approval-flow.spec.ts).
  const bigId = await rpcOk(ctx, 'dl.quotation', 'create', [{
    partner_id: partner.id,
    line_ids: [[0, 0, { name: 'Ghế sắt sơn tĩnh điện GS-100 (đơn hàng dự án)', qty: 30, price_unit: 850000 }]],
  }]);
  const bigAfterCreate = (await rpcOk(ctx, 'dl.quotation', 'read', [[bigId], ['approval_state', 'approval_required']]))[0];
  console.log(`[staging] BF03-004 vế 2a (ngay sau create): báo giá lớn id=${bigId}, approval_state=${bigAfterCreate.approval_state} (kỳ vọng vẫn not_required — gap thật)`);
  expect(bigAfterCreate.approval_state, 'create() không tự đánh giá lại — vẫn not_required ngay sau tạo (gap thật đã ghi nhận)').toBe('not_required');

  // write() với field trong _REEVAL_TRIGGER_FIELDS (discount_pct) — có mặt trong vals là đủ để
  // kích hoạt _reevaluate_approval(), không cần đổi giá trị (đã xác nhận ở stg-bf04-approval-flow.spec.ts).
  await rpcOk(ctx, 'dl.quotation', 'write', [[bigId], { discount_pct: 0.0 }]);
  const bigAfterWrite = (await rpcOk(ctx, 'dl.quotation', 'read', [[bigId], ['approval_state', 'approval_required', 'state']]))[0];
  console.log(`[staging] BF03-004 vế 2b (sau write): approval_state=${bigAfterWrite.approval_state}, approval_required=${bigAfterWrite.approval_required}`);
  expect(bigAfterWrite.approval_required, 'sau write(), báo giá vượt ngưỡng phải chuyển approval_required=true').toBeTruthy();
  expect(bigAfterWrite.approval_state, 'sau write(), approval_state phải chuyển pending').toBe('pending');

  await ctx.dispose();
});
