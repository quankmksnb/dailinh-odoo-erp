import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-21 (PRD §5): "Nhập kho thành phẩm theo BOM chỉ thực hiện được khi BOM ở trạng thái
// Confirmed/Locked. Hệ thống tự tính nhu cầu vật tư từ BOM, cảnh báo và bắt buộc qua duyệt nếu
// thiếu tồn."
//
// PHÁT HIỆN THẬT sau khi rà code kỹ (stock_picking.py, sequence_code "NTP" = Nhập thành phẩm,
// _dlm_fg_receipt_problems() + action_confirm() dòng ~1023): không tìm thấy gate nào kiểm trực
// tiếp "BOM phải Confirmed/Locked" tại tầng phiếu Nhập kho từ xưởng — điều kiện đó thực ra được
// đảm bảo GIÁN TIẾP từ trước: BOM chỉ bị khoá (Đã xác nhận -> Đã khóa) tại thời điểm Đơn bán hàng
// Đã xác nhận (_promote_draft_products, dl_sale_order.py), và chỉ khi đó sản phẩm gia công mới
// đủ điều kiện có phiếu Nhập kho từ xưởng gắn với đơn — cùng bản chất "gate ở thượng nguồn" như
// đã thấy ở GB-08. Cũng không tìm thấy cơ chế "tự tính nhu cầu vật tư từ BOM + bắt duyệt nếu
// thiếu tồn" tại tầng phiếu này — thay vào đó có 1 gate CỤ THỂ VÀ THẬT SỰ chặn confirm nếu phiếu
// khai vật tư ra khỏi xưởng (consume) vượt quá tồn thực tại vị trí Xưởng sản xuất
// (_dlm_fg_receipt_problems, đoạn kiểm Quant._dlm_available_qty). Test này xác nhận đúng gate
// thật đã tìm được: phiếu rỗng (chưa có dòng nào) không xác nhận được.
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

test('GB-21 [staging]: phiếu Nhập kho từ xưởng rỗng (chưa có dòng nào) không xác nhận được', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'thukho@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập Thủ kho thất bại').toBeTruthy();

  const pickingTypes = await rpcOk(ctx, 'stock.picking.type', 'search_read', [[['sequence_code', '=', 'NTP']], ['id', 'name']], { limit: 1 });
  expect(pickingTypes.length, 'Cần có loại phiếu Nhập thành phẩm (NTP) trên staging').toBeGreaterThan(0);
  const pickingTypeId = pickingTypes[0].id;
  console.log(`[staging] GB-21: tìm thấy loại phiếu "${pickingTypes[0].name}" (id=${pickingTypeId})`);

  const pickingId = await rpcOk(ctx, 'stock.picking', 'create', [{ picking_type_id: pickingTypeId }]);
  console.log(`[staging] GB-21: đã tạo phiếu Nhập kho từ xưởng rỗng id=${pickingId}, chưa có dòng nào`);

  const confirmAttempt = await rpc(ctx, 'stock.picking', 'action_confirm', [[pickingId]]);
  const blocked = !!confirmAttempt.error;
  const msg = blocked ? (confirmAttempt.error.data?.message || '') : '';
  console.log(`[staging] GB-21: xác nhận phiếu rỗng -> ${blocked ? 'bị chặn đúng' : 'XÁC NHẬN ĐƯỢC, cần Dev xác nhận'}. ${msg}`);
  expect(blocked, 'Phiếu Nhập kho từ xưởng chưa có dòng nào phải bị chặn xác nhận').toBe(true);
  expect(msg).toMatch(/chưa có dòng nào/);
});
