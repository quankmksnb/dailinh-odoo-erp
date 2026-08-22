import { test, expect, request as playwrightRequest } from '@playwright/test';

// NFR-P05 [staging] — port từ tests/http/http-flows-attachment-size.spec.ts (dlm_dev). Cùng phát
// hiện: không có enforcement kiểm tra dung lượng file trước khi lưu ir.attachment, ở BẤT KỲ đâu
// trong dlm-erp (đã xác nhận qua grep code). Test này đo lại đúng trên staging (bản deploy thật)
// để xác nhận defect vẫn còn hay đã được vá trong lần deploy này.
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

test('TC-SYS-PERF-P05-001 [staging]: upload file 16MB qua ir.attachment.create — kỳ vọng bị chặn theo PRD §6.1', async () => {
  test.setTimeout(120000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const login = await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'ba@gmail.com', password: PASSWORD });
  expect(login.body.result?.uid).toBeTruthy();

  const quotes = await rpc(ctx, '/web/dataset/call_kw', {
    model: 'dl.quotation', method: 'search_read', args: [[], ['id']], kwargs: { limit: 1 },
  });
  const quoteId = quotes.body.result?.[0]?.id;
  expect(quoteId).toBeTruthy();

  const sizeBytes = 16 * 1024 * 1024;
  const buf = Buffer.alloc(sizeBytes, 'Q');
  const base64 = buf.toString('base64');

  const create = await rpc(ctx, '/web/dataset/call_kw', {
    model: 'ir.attachment',
    method: 'create',
    args: [[{
      name: 'system-test-16mb-attachment-staging.bin',
      res_model: 'dl.quotation',
      res_id: quoteId,
      datas: base64,
    }]],
    kwargs: {},
  });

  try {
    if (create.body.error) {
      console.log('[staging] NFR-P05: file 16MB bị chặn đúng như PRD §6.1:', JSON.stringify(create.body.error).slice(0, 300));
    } else {
      console.log('[staging] NFR-P05: file 16MB được CHẤP NHẬN (không bị chặn) — tái hiện đúng defect đã biết.');
    }
    expect(create.body.error, 'NFR-P05: hệ thống phải từ chối file > 15MB nhưng không có enforcement nào trong code').toBeTruthy();
  } finally {
    const newIds: number[] = Array.isArray(create.body.result) ? create.body.result : [];
    if (newIds.length) {
      await rpc(ctx, '/web/dataset/call_kw', {
        model: 'ir.attachment', method: 'unlink', args: [newIds], kwargs: {},
      });
    }
  }

  await ctx.dispose();
});
