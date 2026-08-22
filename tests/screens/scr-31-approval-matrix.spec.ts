import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// SCR-31 tab "Phê duyệt" › "Ma trận duyệt báo giá" — CEO là 1 trong 2 vai trò duy nhất (cùng
// Admin) được "Áp dụng" trực tiếp / "Ngừng" một mức duyệt, theo đúng comment trong UI:
// "Chỉ Giám đốc/Admin được Áp dụng trực tiếp hoặc Ngừng". Trước đây (Lô 7) chỉ test RBAC menu,
// chưa từng thao tác thật bên trong bảng ma trận.
test.use({ storageState: ROLES.ceo.storageStatePath });

test('CEO bấm "Áp dụng" trên dòng Nháp trùng ngưỡng với dòng Đang áp dụng — bị chặn đúng nghiệp vụ', async ({ page }) => {
  await page.goto('/web#action=316&cids=1&menu_id=67');
  await expect(page.getByRole('button', { name: /Lợi nhuận & chiết khấu/ })).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: /Phê duyệt/ }).last().click();
  await expect(page.getByText('Ma trận phê duyệt theo giá trị báo giá')).toBeVisible({ timeout: 15000 });

  // Dòng "10.000 ₫ / Trưởng kinh doanh / Nháp" trùng cấp duyệt với dòng đã "Đang áp dụng" khác
  // ngưỡng — hệ thống phải CHẶN vì "mỗi cấp duyệt chỉ cần một ngưỡng bắt đầu".
  const draftRow = page.getByRole('row', { name: /10\.000 ₫.*Trưởng kinh doanh.*Nháp/ }).first();
  await expect(draftRow).toBeVisible({ timeout: 15000 });
  await draftRow.getByRole('button', { name: 'Áp dụng' }).click();

  await expect(page.getByText('Không thực hiện được')).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/là thừa/)).toBeVisible();
  await page.getByRole('button', { name: 'Đã hiểu' }).click();
});

test('CEO thấy nút "Sửa đổi"/"Ngừng" trên dòng đang áp dụng (RBAC đúng — chỉ CEO/Admin)', async ({ page }) => {
  await page.goto('/web#action=316&cids=1&menu_id=67');
  await page.getByRole('button', { name: /Phê duyệt/ }).last().click();
  await expect(page.getByText('Ma trận phê duyệt theo giá trị báo giá')).toBeVisible({ timeout: 15000 });

  const activeRow = page.getByRole('row', { name: /Giám đốc.*Đang áp dụng/ }).first();
  await expect(activeRow).toBeVisible({ timeout: 15000 });
  await expect(activeRow.getByRole('button', { name: 'Sửa đổi' })).toBeVisible();
  await expect(activeRow.getByRole('button', { name: 'Ngừng' })).toBeVisible();
});
