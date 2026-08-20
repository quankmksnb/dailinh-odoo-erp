import { test, expect, request as playwrightRequest } from '@playwright/test';

// TC-SYSSEC-004 (Security_DLM_SpotChecks sheet, NFR-SEC04 "Account lockout tạm thời khi
// login fail liên tiếp vượt ngưỡng", PRD §6.2) — trước 2026-08-16 grep dl_base tìm
// "lockout/khoa tam/failed_login" ra 0 kết quả nên bị nghi "chưa cài đặt". Thật ra đây là tính
// năng NATIVE của Odoo 17 CE base (không cần code riêng của dlm-erp): res.users._login_authenticate
// dùng context manager _assert_can_auth() (odoo/addons/base/models/res_users.py dòng ~1250) đếm
// login fail theo remote_addr, mặc định base.login_cooldown_after=5 lần / base.login_cooldown_duration=60s
// — vượt ngưỡng thì AccessDenied ngay cả khi gõ ĐÚNG mật khẩu, cho tới khi hết cooldown.
//
// LƯU Ý: cooldown tính theo remote_addr (IP), KHÔNG theo account — chạy test này sẽ tạm khoá luôn
// mọi login từ máy chạy test (127.0.0.1) trong 60s. File này KHÔNG chung project 'chromium' (không
// đụng auth.setup.ts của các spec khác) và tự chờ hết cooldown trước khi kết thúc để không để lại
// tác dụng phụ cho phiên chạy tiếp theo.
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test.describe('TC-SYSSEC-004: khoá tạm thời sau nhiều lần đăng nhập sai liên tiếp', () => {
  test('N lần sai mật khẩu liên tiếp (N = base.login_cooldown_after) -> lần kế tiếp (dù đúng mật khẩu) vẫn bị chặn do cooldown', async () => {
    test.setTimeout(90000);
    const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });

    // Ngưỡng THẬT của dlm_dev đã xác nhận qua odoo-bin shell (2026-08-17):
    // ir.config_parameter.sudo().get_param('base.login_cooldown_after') = 10 (khác mặc định Odoo
    // là 5). Không đọc động qua RPC vì method get_param cần quyền đọc ir.config_parameter mà
    // admin@dlm.demo (tài khoản demo, không có group Administration/Settings) không có.
    const threshold = 10;

    for (let i = 0; i < threshold; i++) {
      const { body } = await rpc(ctx, '/web/session/authenticate', {
        db: 'dlm_dev',
        login: 'sales1@dlm.demo',
        password: `sai-mat-khau-lockout-test-${i}`,
      });
      expect(body.result?.uid ?? null).toBeNull();
    }

    // Lần kế tiếp — dùng ĐÚNG mật khẩu — vẫn phải bị chặn nếu cooldown đang hoạt động.
    const sixth = await rpc(ctx, '/web/session/authenticate', {
      db: 'dlm_dev',
      login: 'sales1@dlm.demo',
      password: 'Demo@2026',
    });
    const blocked = !sixth.body.result?.uid;
    expect(blocked, 'NFR-SEC04: sau 5 lần sai liên tiếp, lần thứ 6 (dù đúng mật khẩu) phải bị chặn tạm thời — nếu không, cooldown đang tắt (base.login_cooldown_after=0) hoặc không hoạt động').toBeTruthy();

    // Chờ hết cooldown (mặc định 60s) trước khi kết thúc — tránh khoá luôn account thật/máy test
    // cho các phiên chạy Playwright kế tiếp từ cùng IP.
    await ctx.dispose();
    await new Promise((resolve) => setTimeout(resolve, 61000));
  });
});
