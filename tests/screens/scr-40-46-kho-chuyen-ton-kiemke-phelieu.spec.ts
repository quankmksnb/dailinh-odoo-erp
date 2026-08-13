import { test, expect, Page } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-10 Inventory Management — SCR-40 (Chuyển kho nội bộ), SCR-44 (Tồn kho),
// SCR-45 (Lô hàng), SCR-46 (Kiểm kê), SCR-42/43 (Phế liệu).
// UC-077/081/082/079. Module dl_inventory (Kho).
// action_dl_picking_transfer=337, action_dl_stock_quant=341,
// action_dl_stock_lot=342, action_dl_stock_inventory=340,
// action_dl_scrap_quant=343 (dlm_dev).

const SUPPLIER = 'Cong ty TNHH Thep Mien Nam';
const MATERIAL = 'Que han 3.2mm (QA)';

/** Nhận hàng NCC + kiểm "Đạt tất cả" thật qua UI, để có tồn thật cho các test
 * sau trong file này (transfer/kiểm kê đều cần tồn có sẵn ở Kho vật tư). */
async function receiveAndPassQc(page: Page) {
  await page.goto('/web#action=334&model=stock.picking&view_type=list&cids=1&menu_id=207');
  await page.getByRole('button', { name: /Mới/ }).click();
  await expect(page.getByText('Nhận hàng NCC').first()).toBeVisible({ timeout: 15000 });

  const supplierField = page.locator('div[name="partner_id"] input').first();
  await supplierField.click({ force: true });
  await supplierField.fill(SUPPLIER);
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().waitFor({ timeout: 15000 });
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().click();

  await page.getByRole('button', { name: 'Thêm một dòng' }).click();
  let selectedRow = page.locator('.o_selected_row').first();
  const productInput = selectedRow.locator('div[name="product_id"] input');
  await productInput.click({ force: true });
  await productInput.fill(MATERIAL);
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().waitFor({ timeout: 15000 });
  await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().click();
  await selectedRow.locator('div[name="product_uom_qty"] input').fill('20');

  await page.getByRole('button', { name: 'Lưu thủ công' }).click();
  await page.getByRole('button', { name: 'Xác nhận phiếu' }).click();
  await expect(page.getByRole('button', { name: 'Xác nhận nhận hàng' })).toBeVisible({ timeout: 15000 });
  // "Thực nhận" đã tự điền = "Dự kiến" — không cần sửa tay khi nhận đủ số.
  await expect(page.getByRole('cell', { name: '20,0000' }).first()).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Xác nhận nhận hàng' }).click();
  await expect(page.getByRole('button', { name: 'Mở phiếu kiểm' })).toBeVisible({ timeout: 20000 });

  await page.getByRole('button', { name: 'Mở phiếu kiểm' }).click();
  await expect(page.getByText('Kiểm & cất hàng').first()).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Đạt tất cả' }).click();
  await page.getByRole('button', { name: 'Xác nhận kiểm' }).click();
  await expect(page.getByText('Đã cất').first()).toBeVisible({ timeout: 20000 });
}

test.describe('SCR-40 - Chuyển kho nội bộ (role: Thủ kho)', () => {
  test.use({ storageState: ROLES.thu_kho.storageStatePath });

  test('nhận hàng, rồi dùng nút lối tắt "Vật tư ra xưởng" chuyển kho thật', async ({ page }) => {
    test.setTimeout(150000);
    await receiveAndPassQc(page);

    await page.goto('/web#action=337&model=stock.picking&view_type=list&cids=1&menu_id=209');
    await page.getByRole('button', { name: /Mới/ }).click();
    await expect(page.getByRole('button', { name: 'Vật tư ra xưởng' })).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Vật tư ra xưởng' }).click();
    // Preset điền cả 2 vị trí — chờ ô "Từ vị trí" có giá trị trước khi thêm dòng
    // (SM-03: domain product_id chỉ mở khi đã có location_id).
    await expect(page.locator('div[name="location_id"] input').first()).not.toHaveValue('', { timeout: 15000 });

    // "Thêm một dòng" đôi khi không bắt kịp ngay sau lần render lại do preset
    // vừa auto-lưu phiếu — thử lại tới khi dòng sửa (.o_selected_row) xuất hiện.
    const selectedRow = page.locator('.o_selected_row').first();
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.getByRole('button', { name: 'Thêm một dòng' }).click({ force: true });
      if (await selectedRow.count() > 0) break;
      await page.waitForTimeout(1000);
    }
    const productInput = selectedRow.locator('div[name="product_id"] input');
    await productInput.click({ force: true });
    await productInput.fill(MATERIAL);
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().waitFor({ timeout: 15000 });
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().click();
    await selectedRow.locator('div[name="product_uom_qty"] input').fill('5');

    await page.getByRole('button', { name: 'Lưu thủ công' }).click();
    await page.getByRole('button', { name: 'Xác nhận phiếu' }).click();
    await expect(page.getByRole('button', { name: 'Xác nhận chuyển kho' })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Xác nhận chuyển kho' }).click();
    await expect(page.locator('.alert-danger')).toHaveCount(0);
  });
});

test.describe('SCR-44/45 - Tồn kho & Lô hàng (role: Thủ kho)', () => {
  test.use({ storageState: ROLES.thu_kho.storageStatePath });

  test('màn Tồn kho KHÔNG có cột giá vốn/giá trị', async ({ page }) => {
    await page.goto('/web#action=341&model=stock.quant&view_type=list&cids=1&menu_id=206');
    await expect(page.getByRole('columnheader', { name: /Số lượng/ })).toBeVisible({ timeout: 15000 });
    for (const col of [/Giá vốn/, /Giá trị/, /Cost/, /Value/]) {
      await expect(page.getByRole('columnheader', { name: col })).toHaveCount(0);
    }
  });

  test('màn Lô hàng mở được, không lỗi quyền', async ({ page }) => {
    await page.goto('/web#action=342&model=stock.lot&view_type=list&cids=1&menu_id=214');
    await expect(page.getByText('Lô hàng').first()).toBeVisible({ timeout: 15000 });
  });
});

test.describe('SCR-46 - Kiểm kê (role: Thủ kho, không có nhóm Quản lý kho native)', () => {
  test.use({ storageState: ROLES.thu_kho.storageStatePath });

  test('điều chỉnh số đếm và Áp dụng thành công dù không có stock.group_stock_manager', async ({ page }) => {
    test.setTimeout(150000);
    await receiveAndPassQc(page);

    await page.goto('/web#action=340&model=stock.quant&view_type=list&cids=1&menu_id=205');
    await expect(page.getByText('Kiểm kê').first()).toBeVisible({ timeout: 15000 });

    // Mặc định gom nhóm theo Vị trí (search_default_group_location) — mở nhóm
    // "Vật tư & hàng thương mại" (đích của receiveAndPassQc) trước khi tìm dòng.
    const groupHeader = page.getByRole('rowheader', { name: /Vật tư & hàng thương mại \(/ }).first();
    const matchingRows = page.getByRole('row').filter({ hasText: MATERIAL });
    for (let attempt = 0; attempt < 3; attempt++) {
      await groupHeader.click();
      if (await matchingRows.count() > 0) break;
      await page.waitForTimeout(1000);
    }

    // Nhiều lô (tracking=lot) của cùng vật tư có thể ra nhiều dòng quant riêng
    // (mỗi lượt chạy test tự nhận hàng mới) — chỉ cần điều chỉnh 1 dòng CHƯA
    // "Đặt = tồn" (dòng đã áp dụng từ lượt chạy trước sẽ không còn nút này).
    const row = matchingRows.filter({ has: page.getByRole('button', { name: 'Đặt = tồn' }) }).first();
    // "Đặt = tồn" tự điền Tồn thực đếm = Tồn hệ thống (chênh lệch = 0) — đủ để
    // xác nhận trọng tâm test này: nút Áp dụng KHÔNG bị khoá quyền, bất kể có
    // sửa số đếm hay không (K8 patch _apply_inventory).
    await row.getByRole('button', { name: 'Đặt = tồn' }).click();
    // `row` là locator ĐỘNG lọc theo nút "Đặt = tồn" — sau khi bấm, nút đổi
    // thành "Áp dụng"/"Xoá" nên `row` không còn khớp chính dòng vừa sửa. Định vị
    // lại: đúng 1 dòng của vật tư này đang ở trạng thái "chờ áp" tại một thời điểm.
    const rowAwaitingApply = matchingRows.filter({ has: page.getByRole('button', { name: 'Áp dụng' }) }).first();
    await expect(rowAwaitingApply.getByRole('button', { name: 'Áp dụng' })).toBeVisible({ timeout: 15000 });
    await rowAwaitingApply.getByRole('button', { name: 'Áp dụng' }).click();
    // K8: nút Áp dụng KHÔNG bị ẩn/khoá dù Thủ kho không có stock.group_stock_manager.
    await expect(page.locator('.o_notification.bg-danger, .o_error_dialog')).toHaveCount(0);
  });
});

test.describe('SCR-42/43 - Phế liệu (role: Thủ kho)', () => {
  test.use({ storageState: ROLES.thu_kho.storageStatePath });

  test('dải chú thích "không phải lợi nhuận tăng thêm" luôn hiện, không đóng được', async ({ page }) => {
    await page.goto('/web#action=343&model=stock.quant&view_type=list&cids=1&menu_id=212');
    await expect(page.getByText('Tiền bán phế liệu không phải lợi nhuận tăng thêm.')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-o-hide-banner]')).toHaveCount(0);
    // Danh sách rỗng ở dlm_dev (chưa có phế liệu nào cân vào) — nút "Bán phế
    // liệu" (header action) chỉ hiện khi có ≥1 dòng, nên không assert ở đây.
  });
});
