# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: http-staging\stg-nfr-p05-attachment-size.spec.ts >> TC-SYS-PERF-P05-001 [staging]: upload file 16MB qua ir.attachment.create — kỳ vọng bị chặn theo PRD §6.1
- Location: tests\http-staging\stg-nfr-p05-attachment-size.spec.ts:20:5

# Error details

```
Error: NFR-P05: hệ thống phải từ chối file > 15MB nhưng không có enforcement nào trong code

expect(received).toBeTruthy()

Received: undefined
```

# Test source

```ts
  1  | import { test, expect, request as playwrightRequest } from '@playwright/test';
  2  | 
  3  | // NFR-P05 [staging] — port từ tests/http/http-flows-attachment-size.spec.ts (dlm_dev). Cùng phát
  4  | // hiện: không có enforcement kiểm tra dung lượng file trước khi lưu ir.attachment, ở BẤT KỲ đâu
  5  | // trong dlm-erp (đã xác nhận qua grep code). Test này đo lại đúng trên staging (bản deploy thật)
  6  | // để xác nhận defect vẫn còn hay đã được vá trong lần deploy này.
  7  | const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
  8  | const DB = 'dlm_prod';
  9  | const PASSWORD = process.env.DLM_STAGING_PASSWORD;
  10 | 
  11 | async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  12 |   const res = await ctx.post(url, {
  13 |     data: { jsonrpc: '2.0', method: 'call', params },
  14 |     headers: { 'Content-Type': 'application/json' },
  15 |   });
  16 |   const body = await res.json();
  17 |   return { res, body };
  18 | }
  19 | 
  20 | test('TC-SYS-PERF-P05-001 [staging]: upload file 16MB qua ir.attachment.create — kỳ vọng bị chặn theo PRD §6.1', async () => {
  21 |   test.setTimeout(60000);
  22 |   if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  23 |   const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  24 |   const login = await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'ba@gmail.com', password: PASSWORD });
  25 |   expect(login.body.result?.uid).toBeTruthy();
  26 | 
  27 |   const quotes = await rpc(ctx, '/web/dataset/call_kw', {
  28 |     model: 'dl.quotation', method: 'search_read', args: [[], ['id']], kwargs: { limit: 1 },
  29 |   });
  30 |   const quoteId = quotes.body.result?.[0]?.id;
  31 |   expect(quoteId).toBeTruthy();
  32 | 
  33 |   const sizeBytes = 16 * 1024 * 1024;
  34 |   const buf = Buffer.alloc(sizeBytes, 'Q');
  35 |   const base64 = buf.toString('base64');
  36 | 
  37 |   const create = await rpc(ctx, '/web/dataset/call_kw', {
  38 |     model: 'ir.attachment',
  39 |     method: 'create',
  40 |     args: [[{
  41 |       name: 'system-test-16mb-attachment-staging.bin',
  42 |       res_model: 'dl.quotation',
  43 |       res_id: quoteId,
  44 |       datas: base64,
  45 |     }]],
  46 |     kwargs: {},
  47 |   });
  48 | 
  49 |   try {
  50 |     if (create.body.error) {
  51 |       console.log('[staging] NFR-P05: file 16MB bị chặn đúng như PRD §6.1:', JSON.stringify(create.body.error).slice(0, 300));
  52 |     } else {
  53 |       console.log('[staging] NFR-P05: file 16MB được CHẤP NHẬN (không bị chặn) — tái hiện đúng defect đã biết.');
  54 |     }
> 55 |     expect(create.body.error, 'NFR-P05: hệ thống phải từ chối file > 15MB nhưng không có enforcement nào trong code').toBeTruthy();
     |                                                                                                                       ^ Error: NFR-P05: hệ thống phải từ chối file > 15MB nhưng không có enforcement nào trong code
  56 |   } finally {
  57 |     const newIds: number[] = Array.isArray(create.body.result) ? create.body.result : [];
  58 |     if (newIds.length) {
  59 |       await rpc(ctx, '/web/dataset/call_kw', {
  60 |         model: 'ir.attachment', method: 'unlink', args: [newIds], kwargs: {},
  61 |       });
  62 |     }
  63 |   }
  64 | 
  65 |   await ctx.dispose();
  66 | });
  67 | 
```