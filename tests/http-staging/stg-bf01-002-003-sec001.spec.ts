import { test, expect, request as playwrightRequest } from '@playwright/test';

// 3 case còn thiếu evidence trong HTTPFlows_DLM_JSONRPC: TC-SYS-BF01-002 (đăng nhập đúng mật
// khẩu), TC-SYS-BF01-003 (search_read RFQ qua session vừa đăng nhập), TC-SYS-SEC-001 (field
// password không lộ ra qua search_read res.users).
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

test('TC-SYS-BF01-002 + TC-SYS-BF01-003 [staging]: đăng nhập đúng mật khẩu, đọc danh sách RFQ thật', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'ba@gmail.com', password: PASSWORD });
  expect(auth.body.result?.uid, 'đăng nhập đúng mật khẩu phải thành công').toBeTruthy();
  expect(auth.body.result?.name, 'result.name phải có tên user').toBeTruthy();
  console.log(`[staging] TC-SYS-BF01-002: uid=${auth.body.result.uid}, name=${auth.body.result.name}`);

  const list = await rpc(ctx, '/web/dataset/call_kw', {
    model: 'dl.quotation.request', method: 'search_read', args: [[], ['id', 'name']], kwargs: { limit: 5 },
  });
  expect(list.res.status()).toBe(200);
  expect(Array.isArray(list.body.result), 'phải trả về mảng RFQ').toBeTruthy();
  expect(list.body.result.length, 'phải có ít nhất 1 RFQ thật trên staging').toBeGreaterThan(0);
  console.log(`[staging] TC-SYS-BF01-003: đọc được ${list.body.result.length} RFQ thật, ví dụ: ${list.body.result[0].name}`);
  await ctx.dispose();
});

test('TC-SYSSEC-002-HTTP (TC-SYS-SEC-001) [staging]: field password không lộ qua search_read res.users', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'ba@gmail.com', password: PASSWORD });

  const { body } = await rpc(ctx, '/web/dataset/call_kw', {
    model: 'res.users', method: 'search_read', args: [[], ['login', 'password']], kwargs: { limit: 3 },
  });
  const rows = body.result || [];
  const leaked = rows.some((r: any) => typeof r.password === 'string' && r.password.length > 0);
  console.log(`[staging] TC-SYS-SEC-001: đọc ${rows.length} user, field password có lộ = ${leaked}`);
  expect(leaked, 'field password không được xuất hiện có giá trị thật trong response').toBe(false);
  await ctx.dispose();
});
