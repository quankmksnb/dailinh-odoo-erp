import { test, expect, request as playwrightRequest } from '@playwright/test';

// TC-E2E-BF02-006 (sheet E2E_BF_DLM_Playwright) — "Đã khoá vẫn lưu trữ được" (thay đổi thiết kế
// chủ đích: cho phép retire BOM cũ khi đã có bản mới thay thế). Trước đây coi nút "Lưu trữ" hiện
// trên BOM Đã khoá là bug (BUG-L3-003) — nay xlsx đã xác nhận đây là hành vi ĐÚNG, không phải
// bug. dl_technical/models/dl_bom.py action_archive() chỉ chặn khi is_rfq_provisional, KHÔNG
// chặn theo status — xác nhận đúng ở tầng model, không chỉ ở tầng nút UI hiện/ẩn.
//
// LƯU Ý: KHÔNG dùng chung với tests/screens-staging/stg-bf02-remaining.spec.ts (case
// "BF02-005/006" trong file đó) — file đó kiểm NGƯỢC LẠI (assert nút Lưu trữ KHÔNG hiện khi Đã
// khoá, theo hiểu biết CŨ) nên không phải bằng chứng hợp lệ cho case này nữa; cần rà lại
// assertion trong file đó cho khớp với kỳ vọng mới này (việc riêng, chưa làm trong lần sửa này).
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

test('TC-E2E-BF02-006 [staging RPC]: action_confirm -> action_lock -> action_archive đều thành công', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await (await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'kythuat@gmail.com', password: PASSWORD } },
  })).json();
  if (!auth.result?.uid) throw new Error('Đăng nhập thất bại');

  // Sản phẩm gia công có sẵn, KHÔNG phải BOM tạm từ RFQ (is_rfq_provisional) — action_lock/
  // action_archive chặn cứng nếu là BOM tạm. Dòng vật tư dùng is_override=true để bỏ qua cổng
  // §12.4 _dlm_check_material_spec (không phải trọng tâm của case này).
  const product = (await rpcOk(ctx, 'product.product', 'search_read',
    [[['product_kind', '=', 'manufactured']]], { fields: ['id'], limit: 1 }))[0];
  const material = (await rpcOk(ctx, 'product.product', 'search_read',
    [[['product_kind', '=', 'material']]], { fields: ['id'], limit: 1 }))[0];

  const bomId = await rpcOk(ctx, 'dl.bom', 'create', [{
    product_id: product.id,
    line_ids: [[0, 0, {
      material_id: material.id, quantity: 5, is_override: true,
      override_reason: 'RPC test evidence TC-E2E-BF02-006',
    }]],
  }]);
  console.log(`[staging] BF02-006: đã tạo BOM id=${bomId} cho sản phẩm id=${product.id}`);

  await rpcOk(ctx, 'dl.bom', 'action_confirm', [[bomId]]);
  await rpcOk(ctx, 'dl.bom', 'action_lock', [[bomId]]);
  const afterLock = (await rpcOk(ctx, 'dl.bom', 'search_read', [[['id', '=', bomId]]], { fields: ['status'] }))[0];
  expect(afterLock.status, 'sau action_lock phải ở trạng thái locked').toBe('locked');

  // Vế chính của case: lưu trữ khi ĐÃ KHOÁ phải THÀNH CÔNG (không raise UserError).
  await rpcOk(ctx, 'dl.bom', 'action_archive', [[bomId]]);
  const afterArchive = (await rpcOk(ctx, 'dl.bom', 'search_read', [[['id', '=', bomId]]], { fields: ['status'] }))[0];
  console.log(`[staging] BF02-006: BOM id=${bomId} sau action_archive, status=${afterArchive.status}`);
  expect(afterArchive.status, 'BOM Đã khoá phải lưu trữ được thành công (thiết kế chủ đích, không phải bug)').toBe('archived');

  await ctx.dispose();
});
