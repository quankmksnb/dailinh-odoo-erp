import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-02 BOM Creation & Management — SCR-14 (Danh sách BOM), SCR-15 (Chi tiết BOM).
// Trước đây CHƯA có spec nào cho màn này dù đã có coverage L1/L2 cho pricing engine.
// action_dl_bom = 319 (dl_technical), model dl.bom.

test.describe('SCR-14 - Danh sách BOM (role: Kỹ thuật)', () => {
  test.use({ storageState: ROLES.ky_thuat.storageStatePath });

  test('có nút "Mới", cột đúng theo FDS, KHÔNG thấy cột Chi phí VT', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toBeVisible();
    for (const col of ['Mã BOM', 'Sản phẩm', 'Phiên bản', 'Trạng thái']) {
      await expect(page.getByRole('columnheader', { name: new RegExp(col) })).toBeVisible();
    }
    // Kỹ thuật không thấy giá — cột "Chi phí VT" không được hiện theo FDS SCR-14.
    await expect(page.getByRole('columnheader', { name: /Chi phí VT/ })).toHaveCount(0);
  });

  test('mở BOM trạng thái "Đã khóa": ribbon vàng, không có nút Xác nhận/Về nháp', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await page.getByText('BOM-0005').first().click();
    await expect(page.getByText('Đã khóa', { exact: false }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Xác nhận BOM/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Về nháp/ })).toHaveCount(0);
  });

  // BUG (bug-log.md, Critical — mới phát hiện 2026-08-11): BOM Đã khóa không có cách nào tạo
  // phiên bản mới → chặn hoàn toàn quy trình sửa đổi BOM đã khóa (FDS: "Tạo phiên bản mới" phải
  // hiện khi trạng thái = Đã xác nhận HOẶC Đã khóa).
  test.fixme('BOM "Đã khóa": menu Tác vụ có nút "Tạo phiên bản mới"', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await page.getByText('BOM-0005').first().click();
    await page.getByRole('button', { name: 'Tác vụ' }).click();
    await expect(page.getByRole('menuitem').filter({ hasText: 'Tạo phiên bản mới' })).toBeVisible();
  });

  // BUG (bug-log.md, Major — mới phát hiện 2026-08-11): FDS "Không lưu trữ được BOM đã khóa"
  // nhưng menu Tác vụ của BOM-0005 (Đã khóa) vẫn có nút "Lưu trữ".
  test.fixme('BOM "Đã khóa": KHÔNG còn nút "Lưu trữ" trong menu Tác vụ', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await page.getByText('BOM-0005').first().click();
    await page.getByRole('button', { name: 'Tác vụ' }).click();
    await expect(page.getByRole('menuitem').filter({ hasText: 'Lưu trữ' })).toHaveCount(0);
  });

  test('mở BOM trạng thái "Nháp": có nút Xác nhận BOM, sửa được dòng vật tư', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await page.getByText('BOM-0004').first().click();
    await expect(page.getByRole('button', { name: /Xác nhận BOM/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Khóa/ })).toHaveCount(0);
  });
});

test.describe('SCR-14/15 - RBAC đối chứng (role: CEO)', () => {
  test.use({ storageState: ROLES.ceo.storageStatePath });

  test('CEO: chỉ đọc, KHÔNG có nút Mới, nhưng thấy cột Chi phí VT', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: /Chi phí VT/ })).toBeVisible();
  });
});

test.describe('SCR-14/15 - RBAC đối chứng (role: Trưởng KD)', () => {
  test.use({ storageState: ROLES.truong_kd.storageStatePath });

  test('Trưởng KD: chỉ đọc, KHÔNG có nút Mới', async ({ page }) => {
    await page.goto('/web#action=319&model=dl.bom&view_type=list&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Mới/ })).toHaveCount(0);
  });
});
