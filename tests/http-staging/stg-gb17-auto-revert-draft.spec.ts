import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-17 (PRD §5): "Nếu báo giá phát sinh thay đổi điều kiện cần duyệt sau khi đã duyệt nội
// bộ/đã gửi khách, báo giá tự động chuyển về trạng thái Nháp."
//
// Rà code (dl_sale/models/dl_quotation.py, _reevaluate_approval() dòng ~761): cơ chế này CÓ THẬT
// trong code, nhưng comment của chính dev ghi rõ "Tình huống này chỉ xảy ra khi ghi thẳng qua
// RPC — trên form các field đó đã khoá ngoài Nháp" (đúng theo GB-02). Vì vậy test này viết ở
// tầng HTTP-flow (RPC trực tiếp), không phải browser E2E — giống tiền lệ TC-SYS-BF03-001 đã làm
// trên dlm_dev cho tình huống tương tự.
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

async function rpc(ctx: any, model: string, method: string, args: unknown[], kwargs: Record<string, unknown> = {}) {
  const res = await ctx.post('/web/dataset/call_kw', {
    data: { jsonrpc: '2.0', method: 'call', params: { model, method, args, kwargs } },
  });
  const body = await res.json();
  if (body.error) throw new Error(`RPC ${model}.${method} lỗi: ${JSON.stringify(body.error.data?.message || body.error)}`);
  return body.result;
}

test('GB-17 [staging]: báo giá Đã gửi khách tự quay về Nháp khi tăng đơn giá vượt ngưỡng qua RPC', async () => {
  test.setTimeout(60000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });

  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'ba@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập Sales thất bại').toBeTruthy();

  // Tìm 1 khách hàng có sẵn để gắn báo giá test.
  const partners = await rpc(ctx, 'res.partner', 'search_read', [[['partner_role', '=', 'customer']], ['id']], { limit: 1 });
  expect(partners.length, 'Cần ít nhất 1 khách hàng trên staging để tạo báo giá test').toBeGreaterThan(0);
  const partnerId = partners[0].id;

  // Bước 1: tạo báo giá GIÁ TRỊ NHỎ (chắc chắn dưới mọi ngưỡng duyệt) — approval_state phải là
  // "not_required" ngay từ đầu.
  const quoteId = await rpc(ctx, 'dl.quotation', 'create', [{
    partner_id: partnerId,
    line_ids: [[0, 0, { name: 'GB-17 test: dòng giá trị nhỏ', qty: 1, price_unit: 100000 }]],
  }]);
  const [afterCreate] = await rpc(ctx, 'dl.quotation', 'read', [[quoteId], ['state', 'approval_state']]);
  console.log(`[staging] GB-17: tạo báo giá id=${quoteId}, state=${afterCreate.state}, approval_state=${afterCreate.approval_state}`);
  expect(afterCreate.approval_state, 'Báo giá giá trị nhỏ phải không cần duyệt ngay từ đầu').toBe('not_required');

  // Bước 2: gửi khách hàng (action_send) — từ Nháp, không cần duyệt nên gửi thẳng được.
  await rpc(ctx, 'dl.quotation', 'action_send', [[quoteId]]);
  const [afterSend] = await rpc(ctx, 'dl.quotation', 'read', [[quoteId], ['state']]);
  console.log(`[staging] GB-17: sau action_send, state=${afterSend.state}`);
  expect(afterSend.state, 'Báo giá phải chuyển "sent" sau khi gửi khách').toBe('sent');

  // Bước 3: sửa THẲNG đơn giá dòng qua RPC lên mức chắc chắn vượt ngưỡng duyệt (giống mức đã
  // dùng ở test BF-04: 850.000đ x 30 = 25.500.000đ, vượt ngưỡng Trưởng KD 20.000.001đ).
  const [lineInfo] = await rpc(ctx, 'dl.quotation', 'read', [[quoteId], ['line_ids']]);
  const lineId = lineInfo.line_ids[0];
  await rpc(ctx, 'dl.quotation.line', 'write', [[lineId], { qty: 30, price_unit: 850000 }]);

  // Bước 4: đọc lại báo giá — kỳ vọng state tự quay về "draft" (GB-17).
  const [afterEdit] = await rpc(ctx, 'dl.quotation', 'read', [[quoteId], ['state', 'approval_state', 'amount_total']]);
  console.log(`[staging] GB-17: sau khi sửa đơn giá vượt ngưỡng (tổng ${afterEdit.amount_total}đ), state=${afterEdit.state}, approval_state=${afterEdit.approval_state}`);
  expect(afterEdit.state, 'GB-17: báo giá Đã gửi khách phải tự quay về Nháp khi phát sinh điều kiện cần duyệt sau khi sửa dữ liệu').toBe('draft');
  expect(afterEdit.approval_state, 'approval_state phải chuyển pending sau khi quay về Nháp và phát hiện cần duyệt').toBe('pending');
});
