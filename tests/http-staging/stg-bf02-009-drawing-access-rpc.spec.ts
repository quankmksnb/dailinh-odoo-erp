import { test, expect, request as playwrightRequest } from '@playwright/test';

// TC-E2E-BF02-009 (sheet E2E_BF_DLM_Playwright, BUG-L3-005, Status=Fail — lỗi thật đã biết,
// KHÔNG kỳ vọng Pass). Menu "Bản vẽ kỹ thuật" hiện cho Trưởng KD (dl_technical/views/menus.xml
// groups= có dl_group_sales_manager) nhưng model dl.drawing không có dòng ACL nào cho vai trò
// này (dl_technical/security/ir.model.access.csv) — bấm vào menu sẽ dính AccessError thật. Test
// này xác nhận đúng defect còn tái hiện trên server thật, không phải chứng minh Pass.
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

test('TC-E2E-BF02-009 [staging RPC]: Trưởng KD đọc dl.drawing qua RPC -> AccessError (BUG-L3-005)', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await (await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'truongkd@gmail.com', password: PASSWORD } },
  })).json();
  if (!auth.result?.uid) throw new Error('Đăng nhập thất bại');

  const res = await ctx.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: { model: 'dl.drawing', method: 'search_read', args: [[], ['id', 'name']], kwargs: { limit: 5 } },
    },
  });
  const body = await res.json();
  const errMsg = body.error?.data?.message || body.error?.message || '';
  const errName = body.error?.data?.name || '';
  console.log(`[staging] BF02-009: Trưởng KD đọc dl.drawing qua RPC -> error=${!!body.error}, name="${errName}", message="${errMsg}"`);

  // BUG-L3-005 vẫn tái hiện: kỳ vọng Fail (có AccessError), không phải Pass. Nếu dòng này bất
  // ngờ KHÔNG lỗi (dev đã thêm ACL), đây là tin tốt — cần cập nhật lại Status/Notes trong Report
  // 5.3 thay vì coi là test hỏng.
  expect(body.error, 'kỳ vọng vẫn AccessError (BUG-L3-005 chưa được Dev sửa) — nếu dòng này pass nghĩa là bug đã được fix, cần cập nhật Status trong Report 5.3').toBeTruthy();
  expect(errName).toContain('AccessError');
});
