import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-19 (PRD §5): "Sản phẩm tạm từ RFQ bị chặn thao tác Kích hoạt thủ công (kể cả Admin). Chỉ
// được chính thức hóa khi Kỹ thuật hoàn tất dòng xử lý RFQ tương ứng."
// Rà code: dl_technical/models/dl_product.py action_lifecycle_activate() override — chặn thẳng
// bằng UserError nếu is_rfq_provisional=True, không có nhánh bypass cho role nào (kể cả Admin).
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

test('GB-19 [staging]: Admin/IT KHÔNG kích hoạt thủ công được sản phẩm tạm từ RFQ', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'admin.it@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập Admin/IT thất bại').toBeTruthy();

  const productId = await rpcOk(ctx, 'product.product', 'create', [{
    name: `GB-19 test sản phẩm tạm ${Date.now().toString().slice(-6)}`,
    is_rfq_provisional: true,
    product_kind: 'manufactured',
    dlm_lifecycle_state: 'draft',
  }]);
  console.log(`[staging] GB-19: đã tạo sản phẩm tạm id=${productId} (is_rfq_provisional=true)`);

  const activateAttempt = await rpc(ctx, 'product.product', 'action_lifecycle_activate', [[productId]]);
  const blocked = !!activateAttempt.error;
  console.log(`[staging] GB-19: Admin/IT thử Kích hoạt sản phẩm tạm -> ${blocked ? 'bị chặn đúng như GB-19' : 'KÍCH HOẠT ĐƯỢC — vi phạm GB-19, cần Dev xác nhận'}. ${blocked ? activateAttempt.error.data?.message : ''}`);
  expect(blocked, 'GB-19: Admin/IT KHÔNG được kích hoạt thủ công sản phẩm tạm từ RFQ').toBe(true);

  // Dọn dữ liệu test.
  await rpcOk(ctx, 'product.product', 'unlink', [[productId]]).catch(() => {});
});
