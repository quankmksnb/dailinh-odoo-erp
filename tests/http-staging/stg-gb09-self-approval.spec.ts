import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-09 (PRD §5): "Người tạo báo giá/bảng giá tự phê duyệt hồ sơ của chính mình vẫn được hệ
// thống cho phép" — Enforced by: "So sánh người tạo yêu cầu và người duyệt; nếu trùng thì tự
// động gắn cờ và ghi log cảnh báo". Rà code (dl_config/models/pricing_approval.py,
// action_approve() dòng ~371): field is_self_approval + message_post cảnh báo khớp đúng mô tả.
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

test('GB-09 [staging]: CEO tự tạo + tự duyệt báo giá của chính mình — được cho phép, có gắn cờ + log', async () => {
  test.setTimeout(60000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'ceo@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập CEO thất bại').toBeTruthy();

  const partners = await rpc(ctx, 'res.partner', 'search_read', [[['partner_role', '=', 'customer']], ['id']], { limit: 1 });
  expect(partners.length).toBeGreaterThan(0);
  const partnerId = partners[0].id;

  // CEO tự tạo 1 báo giá vượt ngưỡng (mức Trưởng KD, CEO vẫn duyệt được theo GB-24 vai trò cao
  // hơn duyệt cấp thấp hơn) — chính CEO sẽ là requester.
  const quoteId = await rpc(ctx, 'dl.quotation', 'create', [{
    partner_id: partnerId,
    line_ids: [[0, 0, { name: 'GB-09 test: CEO tự tạo tự duyệt', qty: 30, price_unit: 850000 }]],
  }]);
  await rpc(ctx, 'dl.quotation', 'write', [[quoteId], { discount_pct: 1 }]);

  const [quoteRec] = await rpc(ctx, 'dl.quotation', 'read', [[quoteId], ['name', 'approval_state']]);
  expect(quoteRec.approval_state, 'Báo giá phải vào Chờ phê duyệt sau khi đánh giá lại').toBe('pending');

  const [pendingReq] = await rpc(ctx, 'dl.pricing.approval.request', 'search_read', [
    [['object_label', '=', quoteRec.name], ['state', '=', 'pending']], ['id', 'requester_id'],
  ]);
  expect(pendingReq, `Không tìm thấy yêu cầu duyệt pending cho ${quoteRec.name}`).toBeTruthy();
  console.log(`[staging] GB-09: yêu cầu duyệt id=${pendingReq.id}, requester_id=${JSON.stringify(pendingReq.requester_id)}`);

  // Chính CEO (cùng user vừa tạo) duyệt luôn yêu cầu này.
  await rpc(ctx, 'dl.pricing.approval.request', 'action_approve', [[pendingReq.id]]);

  const [afterApprove] = await rpc(ctx, 'dl.pricing.approval.request', 'read', [[pendingReq.id], ['state', 'is_self_approval', 'resolved_by_id']]);
  console.log(`[staging] GB-09: sau action_approve, state=${afterApprove.state}, is_self_approval=${afterApprove.is_self_approval}, resolved_by=${JSON.stringify(afterApprove.resolved_by_id)}`);

  expect(afterApprove.state, 'GB-09: tự duyệt vẫn phải ĐƯỢC CHO PHÉP (không bị chặn)').toBe('approved');
  expect(afterApprove.is_self_approval, 'GB-09: hệ thống phải gắn cờ is_self_approval=True khi người duyệt trùng người đề xuất').toBe(true);

  // Kiểm tra chatter có ghi log cảnh báo tự duyệt.
  const messages = await rpc(ctx, 'mail.message', 'search_read', [
    [['res_id', '=', pendingReq.id], ['model', '=', 'dl.pricing.approval.request']], ['body'],
  ], { limit: 20, order: 'id desc' });
  const hasWarningLog = messages.some((m: any) => /tự duyệt/i.test(m.body || ''));
  console.log(`[staging] GB-09: chatter có ${messages.length} message, có log cảnh báo "tự duyệt" = ${hasWarningLog}`);
  expect(hasWarningLog, 'GB-09: phải ghi log cảnh báo trong chatter khi tự duyệt').toBe(true);
});
