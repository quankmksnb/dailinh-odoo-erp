import { test, expect, request as playwrightRequest } from '@playwright/test';

// FT-05/GB-07 (PRD): "Quản lý tài khoản người dùng" (Must priority) — tạo tài khoản, gán vai
// trò, khóa hoặc mở lại, đặt lại mật khẩu, chỉ định người duyệt thay. GB-07: tài khoản chỉ được
// vô hiệu hóa (deactivate), không được phép xóa hẳn.
// Trước giờ Report 5.3 chỉ test Sales bị chặn truy cập màn "Quản lý người dùng" (RBAC) — CHƯA có
// test dương tính nào xác nhận Admin thao tác thật được. Màn SCR-04 là OWL client action gọi các
// RPC method dlm_* trên res.users (dl_config/models/res_users.py) — test thẳng các RPC này.
const BASE_URL = process.env.STAGING_BASE_URL || 'https://erp.dailinh.com';
const DB = 'dlm_prod';
const PASSWORD = process.env.DLM_STAGING_PASSWORD;

async function rpc(ctx: any, model: string, method: string, args: unknown[], kwargs: Record<string, unknown> = {}) {
  const res = await ctx.post('/web/dataset/call_kw', {
    data: { jsonrpc: '2.0', method: 'call', params: { model, method, args, kwargs } },
  });
  const body = await res.json();
  if (body.error) throw new Error(`RPC ${model}.${method} lỗi: ${JSON.stringify(body.error.data?.message || body.error)}`);
  return body.result;
}

test('FT-05/GB-07 [staging]: Admin tạo tài khoản, khoá/mở lại, chỉ định người duyệt thay', async () => {
  test.setTimeout(30000);
  if (!PASSWORD) throw new Error('Thiếu DLM_STAGING_PASSWORD');
  const ctx = await playwrightRequest.newContext({ baseURL: BASE_URL });
  const auth = await ctx.post('/web/session/authenticate', {
    data: { jsonrpc: '2.0', method: 'call', params: { db: DB, login: 'admin.it@gmail.com', password: PASSWORD } },
  }).then((r: any) => r.json());
  expect(auth.result?.uid, 'Đăng nhập Admin/IT thất bại').toBeTruthy();

  const login = `gb07.test.${Date.now().toString().slice(-8)}@example.com`;
  const userId = await rpc(ctx, 'res.users', 'dlm_create_user', [{ name: 'GB-07 Test User', login, email: login }]);
  console.log(`[staging] FT-05: Admin tạo tài khoản mới id=${userId} (${login})`);
  expect(userId).toBeTruthy();

  const [afterCreate] = await rpc(ctx, 'res.users', 'read', [[userId], ['active', 'login']]);
  expect(afterCreate.active, 'Tài khoản mới tạo phải active=True').toBe(true);

  // Khoá tài khoản.
  await rpc(ctx, 'res.users', 'dlm_set_active', [userId, false]);
  const [afterLock] = await rpc(ctx, 'res.users', 'read', [[userId], ['active']]);
  console.log(`[staging] FT-05: sau dlm_set_active(false), active=${afterLock.active}`);
  expect(afterLock.active, 'Tài khoản phải active=False sau khi khoá').toBe(false);

  // GB-07: tài khoản khoá vẫn PHẢI CÒN TỒN TẠI (không bị xoá), đọc lại được qua context active_test=False.
  const stillExists = await rpc(ctx, 'res.users', 'search_count', [[['id', '=', userId]]], { context: { active_test: false } });
  console.log(`[staging] FT-05/GB-07: tài khoản đã khoá vẫn còn tồn tại trong DB = ${stillExists === 1}`);
  expect(stillExists, 'GB-07: tài khoản chỉ được vô hiệu hoá, không được xoá hẳn — bản ghi phải còn tồn tại').toBe(1);

  // Mở lại tài khoản.
  await rpc(ctx, 'res.users', 'dlm_set_active', [userId, true]);
  const [afterUnlock] = await rpc(ctx, 'res.users', 'read', [[userId], ['active']]);
  console.log(`[staging] FT-05: sau dlm_set_active(true), active=${afterUnlock.active}`);
  expect(afterUnlock.active, 'Tài khoản phải active=True sau khi mở lại').toBe(true);

  // Chỉ định người duyệt thay (backup approver) — dùng chính Admin làm backup cho user test.
  const adminUid = auth.result.uid;
  await rpc(ctx, 'res.users', 'dlm_set_backup', [userId, adminUid]);
  const [afterBackup] = await rpc(ctx, 'res.users', 'read', [[userId], ['dl_backup_approver_id']]);
  console.log(`[staging] FT-05: sau dlm_set_backup, dl_backup_approver_id=${JSON.stringify(afterBackup.dl_backup_approver_id)}`);
  expect(afterBackup.dl_backup_approver_id && afterBackup.dl_backup_approver_id[0], 'Phải gán đúng người duyệt thay').toBe(adminUid);

  // Dọn dẹp: khoá lại tài khoản test để không để lại tài khoản active thừa trên staging.
  await rpc(ctx, 'res.users', 'dlm_set_active', [userId, false]).catch(() => {});
  console.log(`[staging] FT-05: đã khoá lại tài khoản test ${login} để dọn dẹp.`);
});
