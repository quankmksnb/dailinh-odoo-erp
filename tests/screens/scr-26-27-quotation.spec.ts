import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

test.use({ storageState: ROLES.sales1.storageStatePath });

const QUOTATION_LIST_URL = '/web#action=295&model=dl.quotation&view_type=list&cids=1';

test.describe('SCR-26 - Danh sách báo giá (role: BA/Sales)', () => {
  test('nút "+ Tạo báo giá" hiển thị cho BA/Sales', async ({ page }) => {
    await page.goto(QUOTATION_LIST_URL);
    await expect(page.getByRole('button', { name: /Tạo báo giá/ })).toBeVisible();
  });

  // BUG-06 (bug-log.md): Vào màn không chọn chip nào nhưng danh sách chỉ hiện 16/20 bản ghi
  // (đúng bằng số "Đang xử lý"), không có chip nào được tô là đang chọn để biết vì sao bị lọc.
  test.fixme('mặc định hiển thị đủ số báo giá như chip "Tất cả"', async ({ page }) => {
    await page.goto(QUOTATION_LIST_URL);
    const allChip = page.getByRole('button', { name: /^Tất cả · \d+$/ });
    const allCountText = await allChip.innerText();
    const allCount = allCountText.match(/\d+/)?.[0];
    await expect(page.getByText(new RegExp(`^${allCount} báo giá$`))).toBeVisible();
  });
});

test.describe('SCR-27 - Chi tiết báo giá (role: BA/Sales) — RBAC giá thành [CRITICAL]', () => {
  test('BA/Sales KHÔNG thấy cột Giá thành/đv trong bảng dòng báo giá', async ({ page }) => {
    await page.goto(QUOTATION_LIST_URL);
    await page.getByRole('cell', { name: 'BG/2026/0031' }).click();
    await expect(page.getByRole('columnheader', { name: /Giá thành/ })).toHaveCount(0);
  });

  test('BA/Sales KHÔNG thấy tab "Phân tích giá thành" / bảng Cấu phần giá', async ({ page }) => {
    await page.goto(QUOTATION_LIST_URL);
    await page.getByRole('cell', { name: 'BG/2026/0031' }).click();
    await expect(page.getByRole('tab', { name: /Phân tích giá thành/ })).toHaveCount(0);
    await expect(page.getByText(/Cấu phần giá/)).toHaveCount(0);
  });

  test('BA/Sales thấy chatter trên báo giá', async ({ page }) => {
    await page.goto(QUOTATION_LIST_URL);
    await page.getByRole('cell', { name: 'BG/2026/0031' }).click();
    await expect(page.getByRole('button', { name: 'Gửi tin' })).toBeVisible();
  });

  test('bảng dòng báo giá đúng cột: Loại dòng, Mô tả, SL, Đơn giá, Thành tiền', async ({ page }) => {
    await page.goto(QUOTATION_LIST_URL);
    await page.getByRole('cell', { name: 'BG/2026/0031' }).click();
    for (const col of ['Loại dòng', 'Mô tả', 'SL', 'Đơn giá', 'Thành tiền']) {
      await expect(page.getByRole('columnheader', { name: col })).toBeVisible();
    }
  });
});
