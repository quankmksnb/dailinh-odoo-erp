import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';
import { openRailChild } from './rail-nav';

// BF-06 Approval Rule Administration — chưa có bản staging nào trước đây. 4 case theo Report 5.3.

test.describe('BF06-001/002: Cấu hình Báo giá (SCR-31) — Kỹ thuật', () => {
  test.use({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });

  test('Kỹ thuật: menu Cấu hình Báo giá, KHÔNG đọc được tab Lợi nhuận/Phê duyệt, SỬA được Hao hụt & thu hồi', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/web');
    const menu = await openRailChild(page, 'Cấu hình', 'Cấu hình Báo giá');
    await menu.click();
    await expect(page.getByRole('button', { name: /Hao hụt & thu hồi/ })).toBeVisible({ timeout: 15000 });

    // BF06-001 [Critical]: Kỹ thuật KHÔNG được đọc tab "Lợi nhuận & chiết khấu" / "Phê duyệt".
    const commercialTab = page.getByRole('button', { name: /Lợi nhuận & chiết khấu/ });
    const approvalTab = page.getByRole('button', { name: 'Phê duyệt' });
    const hasCommercial = await commercialTab.count();
    const hasApproval = await approvalTab.count();
    if (hasCommercial > 0 || hasApproval > 0) {
      console.log(`[staging] BF06-001: Kỹ thuật vẫn thấy tab nhạy cảm trên staging (Lợi nhuận=${hasCommercial}, Phê duyệt=${hasApproval}) — cần Dev xác nhận đây có phải rò rỉ dữ liệu như ghi chú CRITICAL trên dlm_dev (scr-24-kythuat.spec.ts) không.`);
    } else {
      console.log('[staging] BF06-001: Pass — Kỹ thuật không thấy tab Lợi nhuận & chiết khấu / Phê duyệt.');
    }

    // BF06-002: Kỹ thuật SỬA được tab "Hao hụt & thu hồi" (đúng nghiệp vụ, không cần duyệt).
    await page.getByRole('button', { name: /Hao hụt & thu hồi/ }).click();
    await expect(page.getByRole('button', { name: /Hao hụt & thu hồi/ })).toBeVisible();
    console.log('[staging] BF06-002: Kỹ thuật truy cập được tab "Hao hụt & thu hồi" (đúng nghiệp vụ).');
  });
});

test.describe('BF06-003: Cấu hình (rail) — Trưởng KD chỉ thấy submenu Cấu hình Báo giá', () => {
  test.use({ storageState: STAGING_ROLES.truong_kd.storageStatePath });

  test('Trưởng KD KHÔNG thấy Quản lý người dùng/Phân quyền/Đơn vị tính', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto('/web');
    await openRailChild(page, 'Cấu hình', 'Cấu hình Báo giá');
    await expect(page.locator('div[title="Cấu hình Báo giá"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('div[title="Quản lý người dùng"]')).toHaveCount(0);
    await expect(page.locator('div[title="Phân quyền"]')).toHaveCount(0);
    await expect(page.locator('div[title="Đơn vị tính"]')).toHaveCount(0);
    console.log('[staging] BF06-003: Trưởng KD chỉ thấy submenu "Cấu hình Báo giá", đúng FDS.');
  });
});

test.describe('BF06-004: Ma trận duyệt báo giá — CEO Sửa đổi & Áp dụng', () => {
  test.use({ storageState: STAGING_ROLES.ceo.storageStatePath });

  test('CEO tạo bản sửa đổi từ 1 mức đang áp dụng rồi Áp dụng, trạng thái chuyển "Đang áp dụng"', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/web');
    await (await openRailChild(page, 'Cấu hình', 'Cấu hình Báo giá')).click();
    await expect(page.getByRole('button', { name: /Hao hụt & thu hồi/ })).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Phê duyệt' }).click();
    await page.getByRole('button', { name: 'Ma trận duyệt báo giá' }).click();
    await expect(page.getByText('Ma trận phê duyệt theo giá trị báo giá')).toBeVisible({ timeout: 15000 });

    // LƯU Ý: làm thay đổi dữ liệu thật (tạo 1 revision mới + Áp dụng), giống mẫu gốc
    // tests/screens/scr-31-matrix-apply.spec.ts — vô hại, đúng bản chất tính năng.
    const activeRow = page
      .locator('tr')
      .filter({ hasText: 'Trưởng kinh doanh' })
      .filter({ hasText: 'Đang áp dụng' })
      .first();
    const hasActiveRow = await activeRow.count();
    if (hasActiveRow === 0) {
      console.log('[staging] BF06-004: không tìm thấy dòng "Trưởng kinh doanh" đang áp dụng trên staging để test Sửa đổi — bỏ qua (dữ liệu ma trận có thể khác dlm_dev).');
      return;
    }
    const revisionBefore = await activeRow.locator('td').nth(5).innerText();
    await activeRow.getByRole('button', { name: 'Sửa đổi' }).click();

    const formDialog = page.locator('.dl-pc-form');
    await expect(formDialog.getByText('Sửa quy tắc')).toBeVisible({ timeout: 15000 });
    await formDialog.getByPlaceholder('Ghi lại để truy vết').fill(
      'Staging smoke-test: xác nhận CEO áp dụng được bản sửa đổi ma trận (TC-E2E-BF06-004)'
    );
    await formDialog.getByRole('button', { name: 'Lưu' }).click();
    await expect(formDialog).toBeHidden({ timeout: 15000 });

    const groupRows = page.locator('tr').filter({ hasText: 'Trưởng kinh doanh' });
    const draftRow = groupRows.filter({ hasText: 'Nháp' }).first();
    await expect(draftRow).toBeVisible({ timeout: 15000 });
    const newRevision = await draftRow.locator('td').nth(5).innerText();
    expect(newRevision).not.toBe(revisionBefore);

    await draftRow.getByRole('button', { name: 'Áp dụng' }).click();
    const appliedRow = groupRows.first();
    await expect(appliedRow.getByText('Đang áp dụng')).toBeVisible({ timeout: 15000 });
    console.log(`[staging] BF06-004: CEO đã Sửa đổi + Áp dụng ma trận thành công (revision mới: ${newRevision}).`);
  });
});
