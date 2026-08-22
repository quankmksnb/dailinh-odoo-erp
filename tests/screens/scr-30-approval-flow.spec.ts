import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-04 Conditional Approval Workflow — click Duyệt/Từ chối THẬT trên form yêu cầu phê duyệt.
// Trước đây (Lô 7) mới chỉ xác nhận danh sách Phê duyệt (SCR-30) hiển thị đúng số liệu, CHƯA
// từng bấm nút Duyệt/Từ chối thật. Test này dùng dữ liệu demo có sẵn (yêu cầu Chờ duyệt mức
// Trưởng kinh doanh) — action=326, model dl.pricing.approval.request.
// LƯU Ý: test này làm thay đổi dữ liệu thật (duyệt 1 yêu cầu) — chấp nhận được vì đúng tinh
// thần "browser thật, không mock" của guide; không rollback vì Playwright E2E không chạy trong
// transaction như TransactionCase L2.

test.describe('SCR-30 - Duyệt yêu cầu phê duyệt (role: Trưởng KD)', () => {
  test.use({ storageState: ROLES.truong_kd.storageStatePath });

  test('mở 1 yêu cầu Chờ duyệt mức Trưởng KD, bấm Duyệt, trạng thái chuyển Đã duyệt', async ({ page }) => {
    await page.goto('/web#action=326&model=dl.pricing.approval.request&view_type=list&cids=1');
    await page.getByRole('button', { name: /Chờ duyệt/ }).click();

    // Lọc lấy đúng 1 dòng mức "Trưởng kinh doanh" (Trưởng KD không được duyệt mức Giám đốc).
    const row = page.getByRole('row').filter({ hasText: 'Trưởng kinh doanh' }).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    await row.click();

    await expect(page.getByRole('button', { name: 'Phê duyệt' })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Phê duyệt' }).click();

    await expect(page.getByText('Đã duyệt', { exact: false }).first()).toBeVisible({ timeout: 15000 });
  });

  test('KHÔNG thấy nút Duyệt/Từ chối trên yêu cầu mức Giám đốc (không được chỉ định thay CEO)', async ({ page }) => {
    await page.goto('/web#action=326&model=dl.pricing.approval.request&view_type=list&cids=1');
    await page.getByRole('button', { name: /Chờ duyệt/ }).click();
    const row = page.getByRole('row').filter({ hasText: 'Giám đốc' }).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    await row.click();
    // FDS: Trưởng KD chỉ duyệt được mức Trưởng KD, KHÔNG duyệt mức Giám đốc trừ khi được chỉ định.
    await expect(page.getByRole('button', { name: 'Phê duyệt' })).toHaveCount(0);
  });
});

test.describe('SCR-30 - Duyệt yêu cầu phê duyệt (role: CEO)', () => {
  test.use({ storageState: ROLES.ceo.storageStatePath });

  test('mở yêu cầu Chờ duyệt mức Giám đốc, bấm Phê duyệt, trạng thái chuyển Đã duyệt', async ({ page }) => {
    await page.goto('/web#action=326&model=dl.pricing.approval.request&view_type=list&cids=1');
    await page.getByRole('button', { name: /Chờ duyệt/ }).click();
    const row = page.getByRole('row').filter({ hasText: 'Giám đốc' }).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    await row.click();

    await expect(page.getByRole('button', { name: 'Phê duyệt' })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Phê duyệt' }).click();
    await expect(page.getByText('Đã duyệt', { exact: false }).first()).toBeVisible({ timeout: 15000 });
  });
});

test.describe('SCR-30 - Admin KHÔNG được duyệt yêu cầu Báo giá vượt ngưỡng (role: Admin/IT)', () => {
  test.use({ storageState: ROLES.admin.storageStatePath });

  // FDS §SCR-30: "Admin không được duyệt báo giá: ... KHÔNG được duyệt yêu cầu 'Báo giá vượt
  // ngưỡng giá trị' và KHÔNG phê duyệt thay đổi ma trận" — RBAC quan trọng, dễ bị vi phạm nếu
  // Admin dùng chung nút Duyệt như CEO.
  test('mở yêu cầu Chờ duyệt bất kỳ, KHÔNG thấy nút Phê duyệt', async ({ page }) => {
    await page.goto('/web#action=326&model=dl.pricing.approval.request&view_type=list&cids=1');
    await page.getByRole('button', { name: /Chờ duyệt/ }).click();
    const firstRow = page.getByRole('row').nth(1);
    await expect(firstRow).toBeVisible({ timeout: 15000 });
    await firstRow.click();
    await expect(page.getByRole('button', { name: 'Phê duyệt' })).toHaveCount(0);
  });
});
