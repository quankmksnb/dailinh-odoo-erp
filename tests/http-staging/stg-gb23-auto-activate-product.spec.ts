import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-23 (PRD §5): "Sản phẩm gia công dạng 'Nháp' trong Đơn bán hàng sẽ tự động nâng trạng thái
// thành 'Đang hoạt động' khi Đơn bán hàng chuyển sang trạng thái 'Đã xác nhận'."
// Rà code: dl_sale_order.py write() gọi _promote_draft_products() khi state -> 'confirmed', set
// dlm_lifecycle_state='active' cho mọi sản phẩm Nháp có mặt trên dòng đơn.
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

test('GB-23 [staging]: sản phẩm gia công Nháp tự nâng "Đang hoạt động" khi Đơn bán hàng Đã xác nhận', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'admin.it@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập Admin/IT thất bại').toBeTruthy();

  const productId = await rpc(ctx, 'product.product', 'create', [{
    name: `GB-23 test sản phẩm gia công Nháp ${Date.now().toString().slice(-6)}`,
    product_kind: 'manufactured',
    dlm_lifecycle_state: 'draft',
  }]);
  const [beforeState] = await rpc(ctx, 'product.product', 'read', [[productId], ['dlm_lifecycle_state']]);
  console.log(`[staging] GB-23: đã tạo sản phẩm id=${productId}, dlm_lifecycle_state ban đầu = "${beforeState.dlm_lifecycle_state}"`);
  expect(beforeState.dlm_lifecycle_state).toBe('draft');

  const partners = await rpc(ctx, 'res.partner', 'search_read', [[['partner_role', '=', 'customer']], ['id']], { limit: 1 });
  expect(partners.length).toBeGreaterThan(0);
  const partnerId = partners[0].id;

  const orderId = await rpc(ctx, 'dl.sale.order', 'create', [{
    partner_id: partnerId,
    line_ids: [[0, 0, { name: 'GB-23 test dòng gia công', qty: 1, price_unit: 500000, product_id: productId, line_type: 'manufactured' }]],
  }]);
  console.log(`[staging] GB-23: đã tạo đơn bán hàng id=${orderId} (draft)`);

  await rpc(ctx, 'dl.sale.order', 'action_confirm', [[orderId]]);
  const [afterConfirm] = await rpc(ctx, 'dl.sale.order', 'read', [[orderId], ['state']]);
  expect(afterConfirm.state, 'Đơn phải chuyển "confirmed" sau action_confirm').toBe('confirmed');

  const [afterActivate] = await rpc(ctx, 'product.product', 'read', [[productId], ['dlm_lifecycle_state']]);
  console.log(`[staging] GB-23: sau khi đơn Đã xác nhận, dlm_lifecycle_state sản phẩm = "${afterActivate.dlm_lifecycle_state}" (kỳ vọng "active")`);
  expect(afterActivate.dlm_lifecycle_state, 'GB-23: sản phẩm gia công Nháp phải tự nâng "active" khi đơn bán hàng Đã xác nhận').toBe('active');

  // Dọn dữ liệu test — không xoá được order/product đã dùng trong đơn thật, bỏ qua nếu lỗi.
});
