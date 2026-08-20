import { test, expect, request as playwrightRequest } from '@playwright/test';

// GB-06 (PRD §5): "Dữ liệu chi phí nội bộ (giá vốn, lãi gộp, markup) chỉ CEO, Trưởng phòng Kinh
// Doanh, Kế toán nội bộ, Admin được xem; Nhân viên Kinh doanh và Kỹ thuật viên không được xem."
// UI đã test Sales (chặn) + CEO (thấy) qua stg-bf03-rbac-giathanh.spec.ts — bổ sung ở đây: Kế
// toán, Trưởng KD, Admin (phải thấy) + Kỹ thuật (phải KHÔNG thấy, GB-06 nêu rõ nhưng chưa test).
// Field thật: dl.quotation.line groups=_COST_GROUPS (ceo, admin, accountant, sales_manager) —
// Odoo tự lược field khỏi kết quả read() nếu user không thuộc group, không báo lỗi.
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;
const COST_FIELDS = ['base_price', 'material_cost', 'operation_cost', 'adjustment_cost', 'total_cost', 'floor_price'];

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
  const body = await res.json();
  if (body.error) throw new Error(`RPC ${model}.${method} lỗi: ${JSON.stringify(body.error.data?.message || body.error)}`);
  return body.result;
}

test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
});

async function findCostLineId(): Promise<number> {
  const ctx = await login('admin.it@gmail.com');
  const lines = await rpc(ctx, 'dl.quotation.line', 'search_read', [[], ['id']], { limit: 1, order: 'id desc' });
  expect(lines.length, 'Cần ít nhất 1 dòng báo giá trên staging để test GB-06').toBeGreaterThan(0);
  return lines[0].id;
}

for (const [roleLabel, roleLogin, shouldSee] of [
  ['Kế toán nội bộ', 'ketoan@gmail.com', true],
  ['Trưởng KD', 'truongkd@gmail.com', true],
  ['Admin/IT', 'admin.it@gmail.com', true],
  ['Kỹ thuật', 'kythuat@gmail.com', false],
] as [string, string, boolean][]) {
  test(`GB-06 [staging]: ${roleLabel} ${shouldSee ? 'PHẢI thấy' : 'KHÔNG được thấy'} dữ liệu giá thành`, async () => {
    test.setTimeout(30000);
    const lineId = await findCostLineId();
    const ctx = await login(roleLogin);
    if (shouldSee) {
      const [line] = await rpc(ctx, 'dl.quotation.line', 'read', [[lineId], COST_FIELDS]);
      const visibleFields = COST_FIELDS.filter((f) => f in line);
      console.log(`[staging] GB-06: ${roleLabel} đọc dòng báo giá id=${lineId} -> thấy field: [${visibleFields.join(', ')}]`);
      expect(visibleFields.length, `${roleLabel} phải thấy đủ các field giá thành theo GB-06`).toBe(COST_FIELDS.length);
    } else {
      // Bảo vệ có thể là AccessError thẳng (chặt hơn) hoặc lược field âm thầm khỏi kết quả read()
      // (Odoo mặc định) — cả 2 đều hợp lệ theo tinh thần GB-06, chỉ cần dữ liệu không lộ ra.
      let visibleFields: string[] = ['(chưa xác định)'];
      let blockedByError = false;
      try {
        const [line] = await rpc(ctx, 'dl.quotation.line', 'read', [[lineId], COST_FIELDS]);
        visibleFields = COST_FIELDS.filter((f) => f in line);
      } catch (e) {
        blockedByError = true;
      }
      console.log(`[staging] GB-06: ${roleLabel} đọc dòng báo giá id=${lineId} -> ${blockedByError ? 'bị chặn bằng AccessError (chặt hơn kỳ vọng, hợp lệ)' : `thấy field: [${visibleFields.join(', ')}]`}`);
      if (!blockedByError) {
        expect(visibleFields.length, `${roleLabel} KHÔNG được thấy field giá thành nào theo GB-06`).toBe(0);
      }
    }
  });
}
