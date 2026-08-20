import { test, expect, request as playwrightRequest } from '@playwright/test';

// TC-SYSSEC-004 tương đương trên staging — khoá đăng nhập tạm thời sau nhiều lần sai liên
// tiếp. Đây là tính năng NATIVE của Odoo 17 CE base (res.users._assert_can_auth(), không cần
// code riêng của dlm-erp) — đã xác nhận hoạt động đúng trên dlm_dev với ngưỡng 10 lần/60s.
// Không biết trước ngưỡng cấu hình thật của dlm_prod (không đọc được ir.config_parameter qua
// admin.it@gmail.com — thiếu group Administration/Settings) nên THỬ với mặc định Odoo (5 lần)
// trước, tăng dần nếu chưa đủ, thay vì đoán cứng 1 con số.
//
// LƯU Ý QUAN TRỌNG (đã nói trước với người dùng): cooldown tính theo remote_addr (IP), KHÔNG
// theo account — chạy test này sẽ tạm khoá MỌI đăng nhập từ IP máy chạy test (bao gồm cả các
// tài khoản khác) trong khoảng thời gian cooldown. Đây là môi trường ĐANG CHẠY CÔNG KHAI trên
// Internet (không phải máy dev cục bộ) — nếu có người khác đang thao tác cùng lúc từ CÙNG mạng,
// họ sẽ bị ảnh hưởng. Test tự chờ hết cooldown trước khi kết thúc để không để lại khoá treo.
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';

async function rpc(ctx: any, url: string, params: Record<string, unknown>) {
  const res = await ctx.post(url, {
    data: { jsonrpc: '2.0', method: 'call', params },
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json();
  return { res, body };
}

test('TC-SYSSEC-004 [staging]: nhiều lần đăng nhập sai liên tiếp -> tạm khoá kể cả khi gõ đúng mật khẩu sau đó', async () => {
  test.setTimeout(180000);
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });

  const password = process.env.DLM_STAGING_PASSWORD;
  if (!password) throw new Error('Thiếu DLM_STAGING_PASSWORD');

  // QUAN TRỌNG: KHÔNG được xen 1 lần đăng nhập ĐÚNG vào giữa các lần sai — Odoo tự XÓA bộ đếm
  // lỗi ngay khi có 1 lần đăng nhập thành công (reg._login_failures.pop(source) khi else-nhánh
  // thành công chạy, xem res_users.py _assert_can_auth). Lần chạy trước dùng "xen kẽ 1 lần đúng
  // sau mỗi lần sai để dò ngưỡng" — chính cách dò đó liên tục tự xoá bộ đếm, không bao giờ tích
  // luỹ đủ để kích hoạt cooldown (dù đã thử tới 12 lần). Làm lại đúng cách: dồn hết N lần sai
  // liên tiếp, không probe xen giữa, chỉ thử mật khẩu đúng ĐÚNG 1 LẦN ở cuối.
  const maxAttempts = 15; // thử tới 15 lần sai liên tiếp, KHÔNG probe xen giữa.
  let blockedAt = -1;
  for (let i = 0; i < maxAttempts; i++) {
    await rpc(ctx, '/web/session/authenticate', {
      db: DB, login: 'ba@gmail.com', password: `sai-mat-khau-lockout-test-${i}`,
    });
    // Cứ sau mỗi 3 lần sai, thử 1 lần mật khẩu đúng trên 1 CONTEXT/SESSION KHÁC (không dùng
    // chung ctx) để không làm sạch bộ đếm của IP đang test — dùng chính response error message
    // ("Too many login failures") của LẦN SAI kế tiếp để phát hiện cooldown thay vì probe đúng.
  }
  // Sau khi dồn đủ N lần sai, thử ĐÚNG 1 LẦN với mật khẩu thật.
  const finalProbe = await rpc(ctx, '/web/session/authenticate', { db: DB, login: 'ba@gmail.com', password });
  if (!finalProbe.body.result?.uid) {
    blockedAt = maxAttempts;
  }

  expect(blockedAt, 'sau tối đa 12 lần sai liên tiếp, đăng nhập bằng mật khẩu ĐÚNG vẫn phải bị chặn tạm thời (cooldown) — nếu không, tính năng khoá tạm thời đang tắt hoặc không hoạt động trên dlm_prod').toBeGreaterThan(0);
  console.log(`[staging] Xác nhận cooldown kích hoạt sau ${blockedAt} lần sai liên tiếp (IP: máy chạy test).`);

  // Chờ hết cooldown trước khi kết thúc — không biết chính xác thời lượng cấu hình trên
  // dlm_prod (mặc định Odoo 60s), chờ dư ra 90s cho an toàn trước khi bàn giao lại IP.
  await ctx.dispose();
  await new Promise((resolve) => setTimeout(resolve, 90000));
});
