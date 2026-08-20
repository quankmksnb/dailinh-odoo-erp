import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';
import { openRailChild } from './rail-nav';

// BF08-002/004 (Critical/High) — cả 2 trên dlm_dev đều Fail do cùng gốc BUG-L3-001
// (ir.model.access cho product.supplierinfo có perm_create=False/perm_write=False với vai trò
// Kế toán). Kiểm tra trực tiếp qua RPC trước (nguồn sự thật, không phụ thuộc UI render), sau đó
// đối chiếu UI.
test.describe('BF08-002/004: Bảng giá Vật tư (SCR-12) — Kế toán', () => {
  test.use({ storageState: STAGING_ROLES.ke_toan.storageStatePath });

  test('RPC: Kế toán có quyền create/write trên product.supplierinfo không', async ({ page }) => {
    test.setTimeout(30000);
    const accessRes = await page.request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: {
          model: 'product.supplierinfo', method: 'check_access_rights',
          args: ['create'], kwargs: { raise_exception: false },
        },
      },
    }).then((r) => r.json());
    const canCreate = accessRes.result;
    const writeRes = await page.request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: {
          model: 'product.supplierinfo', method: 'check_access_rights',
          args: ['write'], kwargs: { raise_exception: false },
        },
      },
    }).then((r) => r.json());
    const canWrite = writeRes.result;
    console.log(`[staging] BF08-002/004: Kế toán check_access_rights product.supplierinfo -> create=${canCreate}, write=${canWrite}`);

    if (!canCreate || !canWrite) {
      console.log('[staging] BF08-002/004: TÁI HIỆN BUG-L3-001 trên staging — Kế toán không có đủ quyền create/write trên product.supplierinfo, đúng như dlm_dev.');
    } else {
      console.log('[staging] BF08-002/004: khác dlm_dev — Kế toán CÓ quyền create/write trên product.supplierinfo trên staging. Cần đối chiếu thêm với UI bên dưới.');
    }
    expect(canCreate && canWrite, 'Kế toán phải có quyền create+write trên product.supplierinfo theo FDS — nếu fail, đây là BUG-L3-001 tái hiện.').toBe(true);
  });

  test('UI: tìm nút "+ Thêm bảng giá NCC" / "Duyệt" / "Áp dụng" trên SCR-12', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await (await openRailChild(page, 'Bảng giá', 'Bảng giá Vật tư')).click();
    await expect(page.getByRole('heading', { level: 1 }).or(page.locator('.o_breadcrumb'))).toBeVisible({ timeout: 15000 });

    const addBtn = page.getByRole('button', { name: /Thêm bảng giá NCC/i });
    const hasAddBtn = await addBtn.count();
    if (hasAddBtn === 0) {
      console.log('[staging] BF08-002: TÁI HIỆN — không tìm thấy nút "+ Thêm bảng giá NCC" trên SCR-12 (nhất quán với BUG-L3-001 / RPC check ở trên).');
    } else {
      console.log('[staging] BF08-002: nút "+ Thêm bảng giá NCC" CÓ hiển thị trên staging.');
    }

    const approveBtn = page.getByRole('button', { name: /Duyệt/i });
    const applyBtn = page.getByRole('button', { name: /Áp dụng/i });
    console.log(`[staging] BF08-002/004: đếm nút trên dòng — Duyệt=${await approveBtn.count()}, Áp dụng=${await applyBtn.count()}`);
  });
});

test.describe('BF08-003 (đối chứng RBAC): Trưởng KD mở SCR-07 chỉ đọc', () => {
  test.use({ storageState: STAGING_ROLES.truong_kd.storageStatePath });

  test('Trưởng KD KHÔNG thấy nút "+ Thêm NCC"', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    // Đây là mục rail top-level không có submenu con — bấm thẳng vào title.
    await page.getByTitle('Nhà cung cấp / Thầu phụ', { exact: true }).click();
    await page.waitForTimeout(1500);
    await expect(page.getByRole('button', { name: /Thêm NCC/i })).toHaveCount(0);
    console.log('[staging] BF08-003: Pass — Trưởng KD không thấy nút "+ Thêm NCC" (action chỉ đọc), đúng FDS.');
  });
});
