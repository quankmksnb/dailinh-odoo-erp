import { test, expect, request as playwrightRequest } from '@playwright/test';

// Security Spot-Checks mức HỆ THỐNG (không lặp lại RBAC per-endpoint đã có ở L2/scr-sec-rbac-session) —
// theo PRD §6.2 NFR-SEC, chỉ test những gì cần môi trường thật (không mock), theo đúng phạm vi
// "spot-check", không phải audit bảo mật toàn diện.
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';

test.describe('NFR-SEC: Tệp đính kèm chỉ truy cập qua endpoint có auth', () => {
  test('TC-SYSSEC-001: tải file PDF báo giá bằng phiên KHÔNG đăng nhập → phải bị chặn', async () => {
    const anonCtx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    // Attachment thật (id=596, Bao_gia_BG_2026_0027.pdf) tạo ra ở BF-05 — thử tải trực tiếp
    // bằng URL /web/content khi CHƯA đăng nhập (không cookie session hợp lệ).
    const res = await anonCtx.get('/web/content/596?download=true');
    const body = await res.text();
    const isRealPdf = body.startsWith('%PDF');
    // Kỳ vọng theo PRD §6.2 ("liên kết tải tệp phải qua kiểm tra quyền tại thời điểm truy cập,
    // không dùng URL công khai tĩnh"): KHÔNG được trả về nội dung PDF thật cho người chưa đăng nhập.
    expect(isRealPdf).toBeFalsy();
    await anonCtx.dispose();
  });
});

test.describe('NFR-SEC: Mật khẩu không bao giờ lộ qua ORM/API', () => {
  test('TC-SYSSEC-002: gọi read() trực tiếp trên chính user đang đăng nhập, field password không trả về', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
    const login = await ctx.post('/web/session/authenticate', {
      data: { jsonrpc: '2.0', method: 'call', params: { db: 'dlm_dev', login: 'sales1@dlm.demo', password: 'Demo@2026' } },
    });
    const loginBody = await login.json();
    const uid = loginBody.result.uid;

    const read = await ctx.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0',
        method: 'call',
        params: {
          model: 'res.users',
          method: 'read',
          args: [[uid], ['login', 'password', 'password_crypt']],
          kwargs: {},
        },
      },
    });
    const body = await read.json();
    // Nếu field không tồn tại/không hợp lệ, Odoo trả lỗi — vẫn PASS vì mục tiêu là không có
    // plaintext password nào bị trả về trong bất kỳ trường hợp nào.
    const record = body.result?.[0];
    if (record) {
      expect(record.password).toBeFalsy();
    }
    expect(body.error || !record?.password).toBeTruthy();
    await ctx.dispose();
  });
});

test.describe('NFR-SEC: Session cookie flags (quan sát, không phải HTTPS thật ở dev)', () => {
  test('TC-SYSSEC-003: ghi nhận thực trạng — môi trường dev KHÔNG chạy HTTPS', async () => {
    // KHÔNG THỂ TEST HTTPS toàn site ở đây vì môi trường dev chỉ chạy HTTP (127.0.0.1:8069).
    // Đây là spot-check MỨC MÔI TRƯỜNG cần staging/production có HTTPS thật — ghi nhận đúng
    // thực trạng thay vì giả lập kết quả không có thật.
    expect(BASE_URL.startsWith('http://')).toBeTruthy();
  });
});
