import { test, expect, request as playwrightRequest } from '@playwright/test';

// TC-SYSSEC-003 (NFR-SEC: HTTPS toàn site) — check thật trên bản đã deploy, không phải giả lập.
// Bản cũ (tests/http/security-spotchecks.spec.ts) chạy trên dev localhost nên KHÔNG THỂ test
// HTTPS thật (tự thừa nhận trong comment của nó) — file này thay thế đúng bằng chứng đó.
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

test('TC-SYSSEC-003 [staging]: toàn site chạy HTTPS thật + cookie session có cờ Secure', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });

  const res = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'ba@gmail.com', password: PASSWORD } },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  expect(body.result?.uid, 'đăng nhập phải thành công để có session cookie').toBeTruthy();

  // 1. Scheme response thật phải là https (không rơi về http, không mixed content).
  expect(res.url().startsWith('https://'), `response URL phải là https, thực tế: ${res.url()}`).toBeTruthy();

  // 2. Cookie session phải có cờ Secure (chỉ gửi qua HTTPS).
  const setCookieHeaders = res.headersArray().filter((h) => h.name.toLowerCase() === 'set-cookie');
  expect(setCookieHeaders.length, 'phải có ít nhất 1 Set-Cookie header (session_id)').toBeGreaterThan(0);
  const sessionCookie = setCookieHeaders.find((h) => /session_id=/.test(h.value));
  expect(sessionCookie, 'phải tìm thấy cookie session_id trong Set-Cookie').toBeTruthy();
  const hasSecureFlag = /;\s*Secure/i.test(sessionCookie!.value);
  console.log(`[staging] TC-SYSSEC-003: response url=${res.url()}, Set-Cookie session_id có cờ Secure=${hasSecureFlag}`);
  expect(hasSecureFlag, `cookie session phải có cờ Secure, thực tế header: ${sessionCookie!.value}`).toBeTruthy();

  await ctx.dispose();
});
