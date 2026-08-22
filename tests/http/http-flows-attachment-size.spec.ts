import { test, expect, request as playwrightRequest } from '@playwright/test';

// NFR-P05 (Performance_DLM sheet) — giới hạn "File upload (bản vẽ/hợp đồng/báo giá) <= 15 MB/file"
// (PRD §6.1). Trước 2026-08-16 chưa test được vì cần file mẫu >15MB. Grep code (dl_technical,
// dl_sale, dl_product, dl_inventory) không thấy bất kỳ chỗ nào kiểm tra kích thước file trước khi
// lưu ir.attachment — nên bài test này KỲ VỌNG phát hiện đúng lỗ hổng đó (không mock, không giả
// định trước kết quả): ghi thẳng 1 file 16MB qua RPC ir.attachment.create (tương đương việc form
// đính kèm ở SCR-15/26/27 gọi xuống) và xác nhận hệ thống có chặn hay không.
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test.describe('NFR-P05: giới hạn file đính kèm 15MB/file', () => {
  test('TC-SYS-PERF-P05-001: upload file 16MB qua ir.attachment.create — kỳ vọng bị chặn theo PRD §6.1', async () => {
    test.setTimeout(60000);
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    const login = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'sales1@dlm.demo',
      password: 'Demo@2026',
    });
    expect(login.body.result?.uid).toBeTruthy();

    // Cần 1 báo giá có thật để gắn attachment vào (res_model/res_id) — không bắt buộc cho việc
    // đo giới hạn dung lượng nhưng phản ánh đúng use case thật (đính kèm hợp đồng/báo giá).
    const quotes = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'dl.quotation',
      method: 'search_read',
      args: [[], ['id']],
      kwargs: { limit: 1 },
    });
    const quoteId = quotes.body.result?.[0]?.id;
    expect(quoteId).toBeTruthy();

    // 16 MB dữ liệu ngẫu nhiên trước khi encode base64 (~21MB sau encode) — vượt mốc 15MB/file.
    const sizeBytes = 16 * 1024 * 1024;
    const buf = Buffer.alloc(sizeBytes, 'Q'); // nội dung lặp, không cần ngẫu nhiên thật cho test này
    const base64 = buf.toString('base64');

    const create = await rpc(ctx, '/web/dataset/call_kw', {
      model: 'ir.attachment',
      method: 'create',
      args: [[{
        name: 'system-test-16mb-attachment.bin',
        res_model: 'dl.quotation',
        res_id: quoteId,
        datas: base64,
      }]],
      kwargs: {},
    });

    try {
      if (create.body.error) {
        // Có chặn (đạt yêu cầu NFR-P05) — ghi log rõ để đối chiếu.
        console.log('NFR-P05: file 16MB bị chặn đúng như PRD §6.1:', JSON.stringify(create.body.error).slice(0, 300));
      }
      // ĐÂY LÀ TRỌNG TÂM CỦA TEST: khẳng định hệ thống PHẢI chặn file vượt 15MB. Grep code trước đó
      // không thấy enforcement nào -> kỳ vọng assertion này FAIL, xác nhận NFR-P05 chưa được cài đặt
      // (không phải lỗi test — đây là bằng chứng thật cho defect cần Dev xác nhận).
      expect(create.body.error, 'NFR-P05: hệ thống phải từ chối file > 15MB nhưng không có enforcement nào trong code').toBeTruthy();
    } finally {
      // Dọn dẹp LUÔN LUÔN nếu lỡ tạo thành công — kể cả khi assertion ở trên throw — không để
      // lại 21MB rác trong DB dev mỗi lần chạy (test này dự kiến Fail cho tới khi Dev vá NFR-P05).
      // create() theo batch API trả về LIST id (vd [619]), không phải 1 số nguyên đơn — unlink
      // cần đúng list đó, không được bọc thêm 1 lớp mảng nữa.
      const newIds: number[] = Array.isArray(create.body.result) ? create.body.result : [];
      if (newIds.length) {
        await rpc(ctx, '/web/dataset/call_kw', {
          model: 'ir.attachment', method: 'unlink', args: [newIds], kwargs: {},
        });
      }
    }

    await ctx.dispose();
  });
});
