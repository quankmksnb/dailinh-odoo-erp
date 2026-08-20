import { test, expect, request as playwrightRequest } from '@playwright/test';

// 4 case còn "Not Run" trên staging của HTTPFlows_DLM_JSONRPC (Report 5.3):
// TC-SYS-BF01-001, TC-SYS-SEC-002, TC-SYS-BF10-001, TC-SYS-BF10-002.
// Port thẳng từ bộ http/ (dlm_dev) sang staging, đổi tài khoản demo (sales1@dlm.demo,
// thukho@dlm.demo) thành tài khoản thật trên staging (ba@gmail.com, thukho@gmail.com).
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
});

test('TC-SYS-BF01-001 [staging]: đăng nhập sai mật khẩu không tạo session hợp lệ', async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const { body } = await rpc(ctx, '/web/session/authenticate', {
    db: DB, login: 'ba@gmail.com', password: 'mat-khau-sai-bf01-001',
  });
  expect(body.result?.uid ?? null, 'đăng nhập sai mật khẩu phải trả về uid null').toBeNull();
  console.log('[staging] TC-SYS-BF01-001: uid =', body.result?.uid ?? null);
  await ctx.dispose();
});

test('TC-SYS-SEC-002 [staging]: session/destroy vô hiệu hoá session cũ', async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'ba@gmail.com', password: PASSWORD });
  expect(auth.body.result?.uid, 'đăng nhập trước khi test destroy phải thành công').toBeTruthy();

  await rpc(ctx, '/web/session/destroy', {});

  const after = await rpc(ctx, '/web/dataset/call_kw', {
    model: 'dl.quotation', method: 'search_read', args: [[], ['id']], kwargs: { limit: 1 },
  });
  const stillWorks = after.res.status() === 200 && !after.body.error;
  expect(stillWorks, 'gọi search_read bằng session đã destroy phải bị từ chối').toBe(false);
  console.log('[staging] TC-SYS-SEC-002: status sau destroy =', after.res.status(), 'error =', !!after.body.error);
  await ctx.dispose();
});

test('TC-SYS-BF10-001 [staging]: scrap_banner không trả result.html khi chưa đăng nhập', async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const { body } = await rpc(ctx, '/dl_inventory/scrap_banner', {});
  expect(body.result?.html, 'anonymous không được thấy result.html').toBeUndefined();
  console.log('[staging] TC-SYS-BF10-001: có result.html?', !!body.result?.html, '| có error?', !!body.error);
  await ctx.dispose();
});

test('TC-SYS-BF10-002 [staging]: scrap_banner trả đúng câu cảnh báo cho Thủ kho, không có nút ẩn', async () => {
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'thukho@gmail.com', password: PASSWORD });
  expect(auth.body.result?.uid, 'đăng nhập Thủ kho thất bại').toBeTruthy();

  const { body } = await rpc(ctx, '/dl_inventory/scrap_banner', {});
  const html = body.result?.html || '';
  expect(html).toContain('Tiền bán phế liệu không phải lợi nhuận tăng thêm.');
  expect(html).not.toContain('data-o-hide-banner');
  console.log('[staging] TC-SYS-BF10-002: html length =', html.length);
  await ctx.dispose();
});
