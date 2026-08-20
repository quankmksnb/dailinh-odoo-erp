import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// Smoke-test bản đã deploy (https://erp.dailinh.com, db dlm_prod) — nhóm AN TOÀN, chỉ đọc,
// không phụ thuộc dữ liệu mẫu cụ thể (không dựa vào mã BOM/báo giá/vật tư nào có sẵn). Đây là
// lần chạy đầu tiên trên môi trường này nên KHÔNG biết chắc seed data trùng khớp dlm_dev tới đâu.

test.describe('[staging] RBAC cơ bản', () => {
  test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });
  test('Kỹ thuật KHÔNG có menu Báo giá/Cấu hình thương mại', async ({ page }) => {
    await page.goto('/web');
    await expect(page.getByTitle('Báo giá', { exact: true })).toHaveCount(0);
  });
});

test.describe('[staging] RBAC cơ bản (role: BA/Sales)', () => {
  test.use({ storageState: STAGING_ROLES.sales.storageStatePath });
  test('BA/Sales KHÔNG có menu Vật tư/Bảng giá NCC', async ({ page }) => {
    await page.goto('/web');
    await expect(page.getByTitle('Bảng giá', { exact: true })).toHaveCount(0);
  });
});

test.describe('[staging] RBAC — Admin/IT không được duyệt báo giá vượt ngưỡng', () => {
  test.use({ storageState: STAGING_ROLES.admin_it.storageStatePath });
  test('mở màn Phê duyệt, nếu có yêu cầu đang chờ thì KHÔNG thấy nút Phê duyệt', async ({ page }) => {
    await page.goto('/web#action=326&model=dl.pricing.approval.request&view_type=list&cids=1');
    const rows = page.getByRole('row');
    if ((await rows.count()) > 1) {
      await rows.nth(1).click();
      await expect(page.getByRole('button', { name: 'Phê duyệt' })).toHaveCount(0);
    }
  });
});

test.describe('[staging] Bảo mật — HTTPS + không lộ mật khẩu qua RPC', () => {
  test.use({ storageState: STAGING_ROLES.admin_it.storageStatePath });

  test('toàn bộ trang chạy qua HTTPS, không có cảnh báo mixed-content', async ({ page }) => {
    const insecureRequests: string[] = [];
    page.on('request', (req) => {
      if (req.url().startsWith('http://') && !req.url().includes('127.0.0.1')) {
        insecureRequests.push(req.url());
      }
    });
    await page.goto('/web');
    await page.waitForTimeout(2000);
    expect(page.url()).toMatch(/^https:\/\//);
    expect(insecureRequests, `Các request KHÔNG qua HTTPS: ${insecureRequests.join(', ')}`).toEqual([]);
  });

  test('res.users.read không lộ field password qua ORM', async ({ page, request }) => {
    const res = await request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: {
          model: 'res.users', method: 'search_read',
          args: [[], ['login', 'password', 'password_crypt']], kwargs: { limit: 3 },
        },
      },
    });
    const body = await res.json();
    const leaked = (body.result || []).some((r: any) => r.password || r.password_crypt);
    expect(leaked).toBeFalsy();
  });
});
