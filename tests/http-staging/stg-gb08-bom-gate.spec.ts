import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-08 (PRD §5): "Khi tạo báo giá từ RFQ, hệ thống chặn ngay nếu dòng gia công chưa có BOM ở
// trạng thái Đã xác nhận hoặc Đã khóa..."
//
// Đã xác nhận qua rà code + test UI trước đó (stg-gb08-create-gate.spec.ts, gặp khó khăn UI với
// sản phẩm BTP nên chuyển hướng): cơ chế THẬT có 2 lớp — (1) wizard xử lý RFQ tự động
// action_confirm() cho BOM Nháp khi Kỹ thuật bấm "Hoàn tất dòng" (auto-fix, không phải chặn
// cứng), và (2) constraint gốc _check_resolved_bom() trên dl.quotation.request.line VẪN chặn
// thẳng bằng ValidationError nếu có ai (kể cả qua RPC, bỏ qua wizard) cố ghi resolved_bom_id trỏ
// tới 1 BOM chưa Đã xác nhận/Đã khóa. Test này xác nhận lớp constraint gốc (2) — đúng nghĩa đen
// câu chữ "hệ thống chặn ngay" của GB-08.
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

test('GB-08 [staging]: ghi thẳng resolved_bom_id trỏ tới BOM còn Nháp phải bị chặn (ValidationError)', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'kythuat@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập Kỹ thuật thất bại').toBeTruthy();

  // Sales tạo RFQ (Kỹ thuật không có quyền create dl.quotation.request) — dùng context riêng.
  const salesCtx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  await salesCtx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'ba@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());

  // Tạo 1 sản phẩm tự sản xuất + 1 BOM Nháp (có 1 dòng vật tư để không dính lỗi "BOM rỗng").
  const productId = await rpcOk(ctx, 'product.product', 'create', [{
    name: `GB-08 test sản phẩm ${Date.now().toString().slice(-6)}`, product_kind: 'manufactured',
  }]);
  const materials = await rpcOk(ctx, 'product.product', 'search_read', [[['product_kind', '=', 'material']], ['id']], { limit: 1 });
  expect(materials.length, 'Cần ít nhất 1 vật tư trên staging').toBeGreaterThan(0);
  const bomId = await rpcOk(ctx, 'dl.bom', 'create', [{
    product_id: productId,
    line_ids: [[0, 0, { material_id: materials[0].id, quantity: 1 }]],
  }]);
  const [bomState] = await rpcOk(ctx, 'dl.bom', 'read', [[bomId], ['status']]);
  console.log(`[staging] GB-08: đã tạo BOM id=${bomId} cho sản phẩm id=${productId}, status="${bomState.status}" (Nháp, cố tình không xác nhận).`);
  expect(bomState.status).toBe('draft');

  // Tạo 1 RFQ + 1 dòng gia công (bỏ qua wizard — Kỹ thuật ghi thẳng qua RPC để test đúng lớp
  // constraint gốc, giống đúng tinh thần "nếu ai đó ghi thẳng qua RPC" mà code đã lường trước).
  const partners = await rpcOk(salesCtx, 'res.partner', 'search_read', [[['partner_role', '=', 'customer']], ['id']], { limit: 1 });
  expect(partners.length).toBeGreaterThan(0);
  // Dòng gia công bắt buộc có Nhóm sản phẩm (product_category_id, nhóm nhánh Thành phẩm) —
  // constraint mới, chưa có lúc viết bản đầu của test này.
  const categories = await rpcOk(ctx, 'product.category', 'search_read', [[['dl_branch', '=', 'finished'], ['parent_id', '!=', false]], ['id']], { limit: 1 });
  expect(categories.length, 'Cần ít nhất 1 Nhóm sản phẩm nhánh Thành phẩm trên staging').toBeGreaterThan(0);
  const rfqId = await rpcOk(salesCtx, 'dl.quotation.request', 'create', [{
    customer_id: partners[0].id,
    line_ids: [[0, 0, {
      product_type: 'manufactured',
      product_name: 'GB-08 test dòng gia công',
      product_category_id: categories[0].id,
      dimension_note: 'Kiểm tra GB-08: chặn BOM Nháp qua RPC trực tiếp',
    }]],
  }]);
  const [rfq] = await rpcOk(ctx, 'dl.quotation.request', 'read', [[rfqId], ['line_ids']]);
  const lineId = rfq.line_ids[0];
  console.log(`[staging] GB-08: đã tạo RFQ id=${rfqId}, dòng id=${lineId}`);

  // Ghi thẳng resolved_product_id + resolved_bom_id (trỏ BOM Nháp) — bỏ qua wizard hoàn toàn.
  const writeAttempt = await rpc(ctx, 'dl.quotation.request.line', 'write', [[lineId], {
    resolved_product_id: productId,
    resolved_bom_id: bomId,
  }]);
  const blocked = !!writeAttempt.error;
  const msg = blocked ? (writeAttempt.error.data?.message || '') : '';
  console.log(`[staging] GB-08: ghi thẳng resolved_bom_id trỏ BOM Nháp -> ${blocked ? 'bị chặn đúng như GB-08' : 'GHI ĐƯỢC — vi phạm GB-08, cần Dev xác nhận'}. ${msg}`);
  expect(blocked, 'GB-08: constraint _check_resolved_bom phải chặn ghi resolved_bom_id trỏ tới BOM chưa Đã xác nhận/Đã khóa').toBe(true);
  expect(msg, 'Thông báo lỗi phải đúng nội dung về trạng thái BOM').toMatch(/Đã xác nhận hoặc Đã khóa/);
});
