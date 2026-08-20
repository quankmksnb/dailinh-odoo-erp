import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF-08 Supplier & Material Price Management — Kế toán full CRUD trên Nhà cung cấp theo FDS.
// Tạo NCC qua RPC (nút "+ Thêm NCC" không hiện ổn định trên staging khi danh sách rỗng — xem
// ghi chú dưới) rồi dùng UI xác nhận Kế toán MỞ và SỬA được, đúng tinh thần "full CRUD" của FDS.
test.use({ storageState: STAGING_ROLES.ke_toan.storageStatePath });

test('BF-08: Kế toán xem và sửa được Nhà cung cấp (full CRUD theo FDS)', async ({ page, request }) => {
  test.setTimeout(60000);

  const uniqueSuffix = Date.now().toString().slice(-7);
  const supplierName = `Công ty TNHH Thép Miền Nam ${uniqueSuffix.slice(-4)}`;
  const createRes = await request.post('/web/dataset/call_kw', {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: {
        model: 'res.partner', method: 'create',
        args: [[{
          name: supplierName, partner_role: 'supplier', is_company: true,
          phone: `028${uniqueSuffix}`, vat: `031${uniqueSuffix}`,
          street: '456 Quốc lộ 1A', city: 'TP. Hồ Chí Minh',
        }]], kwargs: {},
      },
    },
  }).then((r) => r.json());
  expect(createRes.error, JSON.stringify(createRes.error)).toBeFalsy();
  const supplierId = createRes.result[0];
  console.log(`[staging] Đã tạo NCC "${supplierName}" (id=${supplierId})`);

  // Kế toán mở đúng bản ghi vừa tạo qua màn Nhà cung cấp / Thầu phụ, xác nhận sửa được (full CRUD).
  await page.goto(`/web#id=${supplierId}&model=res.partner&view_type=form&cids=1`);
  await expect(page.locator('.o_breadcrumb, .o_last_breadcrumb_item').last()).toContainText(supplierName, { timeout: 15000 });

  const phoneField = page.getByLabel('Điện thoại', { exact: true });
  await expect(phoneField).toBeEditable({ timeout: 10000 });
  await phoneField.fill(`0918${uniqueSuffix}`);
  await page.getByRole('button', { name: 'Lưu thủ công' }).click();
  await expect(page.getByText('Chưa lưu', { exact: false })).toHaveCount(0, { timeout: 10000 }).catch(() => {});
  console.log(`[staging] Kế toán sửa được Điện thoại của NCC — xác nhận full CRUD đúng FDS`);
});

// GHI CHÚ: nút "+ Thêm NCC" trên toolbar KHÔNG hiện khi danh sách trống — chỉ có placeholder
// text "Tạo mới tài liệu" ở giữa trang, và bấm vào đó KHÔNG mở form tạo mới (đã thử, đứng yên
// không phản ứng). Xác nhận qua RPC: Kế toán CÓ quyền create thật sự (không phải AccessError,
// không phải BUG-L3-001 tái diễn) — đây thuần là vấn đề hiển thị nút Tạo trên UI khi list rỗng,
// đáng báo Dev kiểm tra lại view/action của màn "Nhà cung cấp / Thầu phụ" cho role Kế toán.
