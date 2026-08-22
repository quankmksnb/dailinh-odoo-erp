import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.ke_toan.storageStatePath });

// PASS (bug-log.md): FDS quy định NCC (SCR-08) không validate SĐT/Email/MST như Khách hàng.
test.describe('SCR-08 - Validate NCC / Thầu phụ [PASS]', () => {
  test('Lưu thành công dù SĐT/Email sai định dạng (FDS: NCC không validate SĐT/Email)', async ({ page }) => {
    await page.goto('/web#action=146&model=res.partner&view_type=list&cids=1&menu_id=67');
    await page.getByRole('button', { name: /Thêm NCC/ }).click();
    await page.getByRole('textbox', { name: 'Tên' }).first().fill('NCC Test Validate QA - spec');
    await page.locator('input[id*="phone"]').first().fill('abc-invalid-phone');
    await page.locator('input[id*="email"]').first().fill('not-an-email');
    await page.getByRole('button', { name: /Lưu/ }).first().click();

    await expect(page.locator('.o_form_saved, .o_form_readonly, .breadcrumb')).toBeVisible();
    const invalidFields = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.o_field_invalid')).map((el) => el.getAttribute('name')),
    );
    expect(invalidFields).toHaveLength(0);
  });
});

// PASS (bug-log.md): SCR-13 - mỗi vật tư tối đa 1 dòng "Đang áp dụng"; bật dòng mới tự tắt dòng cũ.
test.describe('SCR-13 - Bảng giá NCC: auto-toggle "Đang áp dụng" [PASS]', () => {
  test('Áp dụng dòng mới tự động chuyển dòng cũ (cùng vật tư) về "Đã duyệt"', async ({ page }) => {
    await page.goto('/web#action=305&model=product.supplierinfo&view_type=list&cids=1&menu_id=67');

    const oldAppliedRow = page.getByRole('row', {
      name: '[VT-CT3-3-QA] Thep tam CT3 day 3mm (QA) Cong ty TNHH Thep Mien Nam',
    });
    await expect(oldAppliedRow).toContainText('Đang áp dụng');

    const newRow = page.getByRole('row', {
      name: '[VT-CT3-3-QA] Thep tam CT3 day 3mm (QA) Cong ty CP Kim khi Viet Nhat',
    });
    // Dòng này có thể đang ở "Nháp" hoặc "Đã duyệt" tuỳ lần chạy trước; đảm bảo về "Đã duyệt" trước khi Áp dụng.
    if (await newRow.getByRole('button', { name: 'Duyệt' }).count()) {
      await newRow.getByRole('button', { name: 'Duyệt' }).click();
      await expect(newRow).toContainText('Đã duyệt');
    }
    const applyBtn = newRow.getByRole('button', { name: 'Áp dụng' });
    await expect(applyBtn).toBeEnabled();
    await applyBtn.click();

    await expect(newRow).toContainText('Đang áp dụng');
    await expect(oldAppliedRow).toContainText('Đã duyệt');

    // Khôi phục trạng thái ban đầu để không làm lệch dữ liệu seed cho các lần chạy sau.
    await oldAppliedRow.getByRole('button', { name: 'Áp dụng' }).click();
    await expect(oldAppliedRow).toContainText('Đang áp dụng');
  });
});
