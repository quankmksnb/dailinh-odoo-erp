import { test, expect, request as playwrightRequest } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// Bổ sung 2 spot-check bảo mật còn thiếu trên staging (đã có HTTPS + password không lộ ở
// stg-rbac-spotcheck.spec.ts): TC-SYSSEC-001 (file đính kèm chặn truy cập ẩn danh) và
// TC-E2E-SEC-001 (URL nội bộ chặn đúng theo vai trò).
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';

test('TC-SYSSEC-001 [staging]: file PDF báo giá không tải được khi chưa đăng nhập', async () => {
  const anonCtx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  // Dùng PDF báo giá đã sinh thật từ luồng BF-05 (Bao_gia_BG_2026_0016.pdf, attachment id=72).
  const res = await anonCtx.get('/web/content/72?download=true');
  const body = await res.body();
  const isPdf = body.slice(0, 4).toString('utf-8') === '%PDF';
  expect(isPdf, 'File PDF báo giá KHÔNG được trả về cho request ẩn danh (không có session)').toBeFalsy();
  console.log(`[staging] TC-SYSSEC-001: GET /web/content/72 ẩn danh -> status ${res.status()}, không lộ nội dung PDF thật.`);
  await anonCtx.dispose();
});

test('TC-E2E-SEC-001 [staging]: Kỹ thuật không đọc được model Báo giá qua URL trực tiếp', async ({ browser }) => {
  const ctx = await browser.newContext({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });
  const kyThuatPage = await ctx.newPage();
  const res = await kyThuatPage.request.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: {
        model: 'dl.quotation', method: 'search_read',
        args: [[], ['id', 'name']], kwargs: { limit: 5 },
      },
    },
  });
  const body = await res.json();
  const gotRealData = Array.isArray(body.result) && body.result.length > 0;
  const blocked = !!body.error || !gotRealData;
  expect(blocked, 'Kỹ thuật KHÔNG có ACL đọc dl.quotation — search_read phải bị chặn (lỗi hoặc mảng rỗng), không được trả dữ liệu báo giá thật').toBeTruthy();
  console.log(`[staging] TC-E2E-SEC-001: Kỹ thuật gọi search_read dl.quotation qua RPC trực tiếp -> ${body.error ? 'AccessError đúng như kỳ vọng' : 'mảng rỗng, không lộ dữ liệu'}.`);
  await ctx.close();
});
