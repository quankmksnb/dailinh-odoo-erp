import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-03 (PRD §5): "Để chỉnh sửa báo giá đã duyệt hoặc đang ở luồng khác, người dùng phải sử dụng
// chức năng 'Về nháp'. Hành động này sẽ hủy kết quả duyệt cũ và yêu cầu báo giá phải được duyệt
// lại từ đầu."
//
// Rà code: action_reset_draft() (dl_quotation.py ~1205) chỉ đơn thuần set state='draft', KHÔNG
// tự set lại approval_state — nhưng action_send() vẫn chặn đúng vì điều kiện gửi từ Nháp đòi
// approval_state == 'not_required' (approval_state cũ "approved" không thoả). Test dưới đây xác
// nhận đúng HIỆU QUẢ bảo vệ mà GB-03 mô tả (không gửi thẳng được sau khi Về nháp mà chưa được
// duyệt lại), dù cơ chế thực hiện là "chặn gửi" chứ không phải "xoá sạch approval_state".
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

async function login(login_: string) {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: login_, password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, `Đăng nhập ${login_} thất bại`).toBeTruthy();
  return ctx;
}

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

test('GB-03 [staging]: "Về nháp" sau khi đã duyệt -> không gửi khách thẳng được nếu chưa duyệt lại', async () => {
  test.setTimeout(60000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ceoCtx = await login('ceo@gmail.com');

  const partners = await rpcOk(ceoCtx, 'res.partner', 'search_read', [[['partner_role', '=', 'customer']], ['id']], { limit: 1 });
  expect(partners.length).toBeGreaterThan(0);
  const partnerId = partners[0].id;

  // Tạo + tự duyệt 1 báo giá vượt ngưỡng (như GB-09) để có 1 bản ghi ĐÃ DUYỆT thật, không giả lập.
  const quoteId = await rpcOk(ceoCtx, 'dl.quotation', 'create', [{
    partner_id: partnerId,
    line_ids: [[0, 0, { name: 'GB-03 test: về nháp sau khi đã duyệt', qty: 30, price_unit: 850000 }]],
  }]);
  await rpcOk(ceoCtx, 'dl.quotation', 'write', [[quoteId], { discount_pct: 1 }]);
  const [pendingReq] = await rpcOk(ceoCtx, 'dl.pricing.approval.request', 'search_read', [
    [['object_label', '=', (await rpcOk(ceoCtx, 'dl.quotation', 'read', [[quoteId], ['name']]))[0].name], ['state', '=', 'pending']], ['id'],
  ]);
  await rpcOk(ceoCtx, 'dl.pricing.approval.request', 'action_approve', [[pendingReq.id]]);

  const [afterApprove] = await rpcOk(ceoCtx, 'dl.quotation', 'read', [[quoteId], ['state', 'approval_state']]);
  console.log(`[staging] GB-03: sau khi duyệt, state=${afterApprove.state}, approval_state=${afterApprove.approval_state}`);
  expect(afterApprove.state, 'Báo giá phải ở "approved" sau khi được duyệt').toBe('approved');

  // Bấm "Về nháp".
  await rpcOk(ceoCtx, 'dl.quotation', 'action_reset_draft', [[quoteId]]);
  const [afterReset] = await rpcOk(ceoCtx, 'dl.quotation', 'read', [[quoteId], ['state', 'approval_state']]);
  console.log(`[staging] GB-03: sau "Về nháp", state=${afterReset.state}, approval_state=${afterReset.approval_state}`);
  expect(afterReset.state, 'Báo giá phải về "draft" sau khi bấm Về nháp').toBe('draft');

  // Thử gửi khách NGAY (chưa sửa gì, chưa duyệt lại) — GB-03 kỳ vọng bị CHẶN.
  const sendAttempt = await rpc(ceoCtx, 'dl.quotation', 'action_send', [[quoteId]]);
  const blocked = !!sendAttempt.error;
  console.log(`[staging] GB-03: thử gửi khách ngay sau Về nháp (chưa duyệt lại) -> ${blocked ? 'bị chặn đúng như GB-03' : 'GỬI ĐƯỢC — có thể là gap thật, cần Dev xác nhận'}. ${blocked ? sendAttempt.error.data?.message : ''}`);
  expect(blocked, 'GB-03: báo giá vừa "Về nháp" từ trạng thái Đã duyệt phải bị chặn gửi khách cho tới khi được duyệt lại từ đầu').toBe(true);
});
