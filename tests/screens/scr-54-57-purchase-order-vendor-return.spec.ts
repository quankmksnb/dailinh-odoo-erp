import { test, expect, Page } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-11 Purchase Requisition & Procurement — SCR-54 (Danh sách đơn mua hàng),
// SCR-55 (Chi tiết đơn mua hàng), SCR-56 (Danh sách Trả hàng NCC), SCR-57
// (Chi tiết Trả hàng NCC). Model `dl.purchase.order` (SCR-54/55) và
// `stock.picking` lọc loại TR (SCR-56/57). Module dl_purchase (Mua hàng) —
// trước bản này CHƯA có spec L3 nào cho cả bốn màn; SCR-56 chỉ có một test
// xác nhận mở được màn, không thao tác gì (scr-36-39-kho-nhan-kiem.spec.ts).
//
// Đi bằng rail (getByTitle), không dùng action=/menu_id= cứng: ba màn này
// chưa từng có test nào ghi số action/menu thật, và rail là đường thật user
// đi (menu_dl_purchase_order, menu_dl_purchase_rfq_queue,
// dl_inventory.menu_dl_picking_vendor_return — mục cuối đã dời sang rail Mua
// hàng bằng <record> ghi đè parent_id, xem dl_purchase/views/menus.xml).
//
// Cũng đi kèm một test nhẹ cho action_dl_purchase_rfq_queue ("Hỏi giá chờ trả
// lời") — màn có thật, có domain lọc riêng, nhưng KHÔNG có mã màn hình trong
// FDS hiện hành.

const SUPPLIER = 'Cong ty TNHH Thep Mien Nam';
const MATERIAL = 'Thep tam CT3 day 3mm (QA)';

/** Mở một mục con của rail (vd nhóm "Mua hàng" hoặc "Kho"). Bấm mục cha để xổ
 * submenu rồi bấm mục con — nhưng rail phát badge (đếm việc chờ) bằng ORM
 * async ngay lúc mount, và nếu badge về tới đúng lúc đang bấm thì Owl render
 * lại rail, mục cha bị thay node giữa chừng và cú bấm "rơi" mất (submenu đứng
 * yên đóng, hoặc bật rồi tắt ngay). Thử lại vài lần thay vì bấm đúng một phát
 * cho chắc. */
async function openRailChild(page: Page, parentTitle: string, childTitle: string) {
  const child = page.getByTitle(childTitle, { exact: true });
  for (let attempt = 0; attempt < 6; attempt++) {
    if (await child.isVisible().catch(() => false)) {
      await child.click();
      return;
    }
    await page.getByTitle(parentTitle, { exact: true }).click();
    await page.waitForTimeout(400);
  }
  await child.click({ timeout: 15000 });
}

async function openPurchaseChild(page: Page, childTitle: string) {
  await openRailChild(page, 'Mua hàng', childTitle);
}

test.describe('SCR-54 - Danh sách Đơn mua hàng (role: Mua hàng)', () => {
  test.use({ storageState: ROLES.mua_hang.storageStatePath });

  test('mở được menu, có ít nhất một đơn thật và đủ cột theo FDS', async ({ page }) => {
    await page.goto('/web');
    await openPurchaseChild(page, 'Đơn mua hàng');

    // Danh sách "Đang chạy" (mặc định) rỗng thì Odoo 17 KHÔNG vẽ header bảng
    // — chỉ hiện màn hình rỗng, nên phải có ít nhất một đơn thật mới soi được
    // cột. Tạo tay một đơn nháp tối thiểu qua UI, không cần chốt.
    await page.getByRole('button', { name: /Mới/ }).click();
    const supplierField = page.locator('div[name="partner_id"] input').first();
    await supplierField.click({ force: true });
    await supplierField.fill(SUPPLIER);
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().waitFor({ timeout: 15000 });
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().click();
    await page.getByRole('button', { name: 'Lưu thủ công' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/PO\/\d{4}\//, { timeout: 15000 });

    await openPurchaseChild(page, 'Đơn mua hàng');
    for (const col of ['Số đơn', 'Nhà cung cấp', 'Ngày lập', 'Hàng về dự kiến', 'Tổng tiền', 'Trạng thái']) {
      await expect(page.getByRole('columnheader', { name: col })).toBeVisible({ timeout: 15000 });
    }
  });
});

test.describe('SCR-54 - Vai trò không có ACL (role: Kỹ thuật)', () => {
  test.use({ storageState: ROLES.ky_thuat.storageStatePath });

  test('rail không có mục "Mua hàng" — Kỹ thuật không có dòng ACL nào cho dl.purchase.order', async ({ page }) => {
    await page.goto('/web');
    await expect(page.getByTitle('Mua hàng')).toHaveCount(0);
  });
});

test.describe('SCR-55/56/57 - Tạo đơn mua, chốt, nhận hàng, kiểm loại một phần, trả NCC (role: Mua hàng)', () => {
  test.use({ storageState: ROLES.mua_hang.storageStatePath });

  test('luồng thật: lập đơn mua, chốt đơn, nhận đủ hàng, kiểm loại một phần, phiếu trả NCC tự sinh và chốt được', async ({ page, browser }) => {
    test.setTimeout(180000);

    // --- SCR-55: tạo đơn mua thật qua UI ---
    await page.goto('/web');
    await openPurchaseChild(page, 'Đơn mua hàng');
    await page.getByRole('button', { name: /Mới/ }).click();

    const supplierField = page.locator('div[name="partner_id"] input').first();
    await supplierField.click({ force: true });
    await supplierField.fill(SUPPLIER);
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().waitFor({ timeout: 15000 });
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: SUPPLIER }).first().click();

    // Ngày hàng về dự kiến bắt buộc để chốt được (_dlm_check_confirmable) —
    // lấy lại đúng định dạng ngày mà "Ngày lập" đang hiện (context_today) thay
    // vì đoán định dạng theo locale, tránh gõ sai định dạng làm ô không nhận.
    const today = await page.locator('div[name="date_order"] input').first().inputValue();
    const dateExpectedInput = page.locator('div[name="date_expected"] input').first();
    await dateExpectedInput.fill(today);
    await dateExpectedInput.press('Tab');

    await page.getByRole('button', { name: 'Thêm một dòng' }).click();
    const selectedRow = page.locator('.o_selected_row').first();
    const productInput = selectedRow.locator('div[name="product_id"] input');
    await productInput.click({ force: true });
    await productInput.fill(MATERIAL);
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().waitFor({ timeout: 15000 });
    await page.locator('.o-autocomplete--dropdown-menu li', { hasText: MATERIAL }).first().click();
    await selectedRow.locator('div[name="qty"] input').fill('50');

    await page.getByRole('button', { name: 'Lưu thủ công' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/PO\/\d{4}\//, { timeout: 15000 });

    // Đơn mua chủ động (không từ báo giá) nên dlm_customer_committed luôn
    // đúng — nút Chốt đơn sáng ngay từ Nháp, không cần Gửi hỏi giá trước.
    await page.getByRole('button', { name: 'Chốt đơn' }).click();

    // action_dlm_confirm trả về action mở THẲNG phiếu nhận vừa sinh (phiếu đã
    // action_confirm + action_assign ở server) — khẳng định đơn mua nối đúng
    // sang Kho, không phải chỉ đổi trạng thái rồi đứng yên trên đơn mua.
    // "Thực nhận" đã tự điền = "Dự kiến" khi phiếu ở trạng thái Chờ nhận —
    // nhưng cả hai nút xử lý phiếu này (Xác nhận phiếu/Xác nhận nhận hàng) đều
    // groups="...warehouse,...admin" trên view_dl_receipt_form, Mua hàng
    // KHÔNG có mặt: kiểm soát chéo đặt hàng/nhận hàng đúng như dl_purchase_order.py
    // _dlm_check_buyer nói ngược lại (Thủ kho không đặt hàng). Mua hàng chỉ
    // ĐỌC được phiếu vừa sinh, không thao tác — canh đúng ranh giới đó ở đây.
    // Chờ ĐÚNG heading của phiếu nhận (mẫu "DL/NH/xxxxx") thay vì chỉ chờ một
    // dòng chứa "50" — dòng đó đã có sẵn ngay trên đơn mua (tab "Hàng đặt
    // mua") nên chờ nhầm nó sẽ pass giả trước khi trang kịp điều hướng sang.
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/NH\//, { timeout: 20000 });
    const receiptName = (await page.getByRole('heading', { level: 1 }).textContent())?.trim() || '';
    expect(receiptName).toMatch(/\//);
    await expect(
      page.getByRole('row', { name: new RegExp(MATERIAL.replace(/[()]/g, '\\$&')) }),
    ).toContainText('50');
    await expect(page.getByRole('button', { name: 'Xác nhận nhận hàng' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Xác nhận phiếu' })).toHaveCount(0);

    // --- Đổi vai sang Thủ kho (context riêng, storageState khác) để nhận
    // hàng + kiểm — đúng người thật làm việc này trên màn Kho, không phải
    // Mua hàng. Tìm đúng phiếu vừa sinh bằng tên (mỗi lần chạy test sinh số
    // phiếu mới, không đụng phiếu của lần chạy trước). ---
    const whContext = await browser.newContext({ storageState: ROLES.thu_kho.storageStatePath });
    const wh = await whContext.newPage();
    await wh.goto('/web');
    await openRailChild(wh, 'Kho', 'Nhận hàng');
    await wh.locator('.o_searchview_input').first().fill(receiptName);
    await wh.locator('.o_searchview_input').first().press('Enter');
    await wh.getByRole('cell', { name: receiptName }).first().click();
    await expect(wh.getByRole('button', { name: 'Xác nhận nhận hàng' })).toBeVisible({ timeout: 15000 });
    // "Thực nhận" tự điền = "Dự kiến" khi phiếu vào Chờ nhận — hiện dạng số
    // trần "50" ở chế độ xem tĩnh (khác widget dl_qty đủ 4 số thập phân khi ở
    // chế độ sửa, như khi tự gõ tay ở các spec Kho khác).
    await expect(
      wh.getByRole('row', { name: new RegExp(MATERIAL.replace(/[()]/g, '\\$&')) }),
    ).toContainText('50');
    await wh.getByRole('button', { name: 'Xác nhận nhận hàng' }).click();
    await expect(wh.getByRole('button', { name: 'Mở phiếu kiểm' })).toBeVisible({ timeout: 20000 });
    await wh.getByRole('button', { name: 'Mở phiếu kiểm' }).click();
    await expect(wh.getByText('Kiểm & cất hàng').first()).toBeVisible({ timeout: 15000 });

    // Kiểm KHÔNG đạt một phần (10/50) — đường sinh phiếu Trả NCC thật duy
    // nhất, khác hẳn "Đạt tất cả" mà các spec Kho hiện có đã dùng.
    //
    // 🔴 PHÁT HIỆN THẬT (báo lại trong report, không tự sửa ở đây): sửa tay
    // trực tiếp ô "Đạt"/"Loại" mà KHÔNG bấm "Đạt tất cả" trước để lại
    // move.picked=False trên dòng — không có onchange nào ở
    // dl_inventory/models/stock_move.py bật cờ này khi gõ tay (chỉ hai nút
    // "Đạt tất cả"/"Khớp lại số" mới set `picked: True`). stock.picking
    // core (button_validate, dòng ~1258 stock_picking.py) coi dòng
    // picked=False là CHƯA XỬ LÝ bất kể số đã khớp, nên toàn bộ phần ĐẠT (40)
    // bị tách sang một phiếu kiểm backorder mới ở trạng thái "assigned" thay
    // vì được xác nhận cùng phiếu — cất kho coi như KHÔNG xảy ra cho phần
    // đạt, dù UI báo "Đã kiểm đạt toàn bộ và cất vào kho". Đã tự kiểm chứng
    // bằng SQL (bảng stock_move) khi viết spec này.
    //
    // Né lỗi trên bằng cách bấm "Đạt tất cả" trước (set picked=True cho mọi
    // dòng, đúng như luồng người dùng thật hay đi: đạt hết rồi mới sửa lại
    // đúng dòng có hàng lỗi) rồi mới hạ Đạt/nâng Loại trên dòng đó — picked
    // vẫn giữ True vì không onchange nào tắt lại nó khi sửa số.
    await wh.getByRole('button', { name: 'Đạt tất cả' }).click();

    // Đơn chỉ có một mặt hàng nên phiếu kiểm chỉ có đúng một dòng — lấy thẳng
    // dòng đầu, không lọc theo tên mặt hàng: ô "Mặt hàng" hiện bị CSS cắt chữ
    // (hiện "Thep tam CT3 day …"), text node trong DOM cũng cắt theo nên lọc
    // hasText khớp cả tên đầy đủ sẽ không bao giờ trúng.
    //
    // 🔴 Dòng này tự render LẠI một lần ngay sau khi vào màn (cột đổi thứ tự,
    // datapoint đổi id — chắc là do tải lô/tồn kho xong mới xếp lại cột) —
    // bấm sớm quá thì click rơi đúng lúc DOM bị thay, không vào được chế độ
    // sửa. Chờ cột "dlm_qty_rejected" (chỉ có ở bản render CUỐI) xuất hiện
    // rồi mới bấm, và tự thử lại nếu vẫn lỡ trúng nhịp thay DOM.
    await wh.locator('.o_data_row td[name="dlm_qty_rejected"]').first().waitFor({ timeout: 15000 });
    const qcSelectedRow = wh.locator('.o_selected_row').first();
    let qcEditReady = false;
    for (let attempt = 0; attempt < 5 && !qcEditReady; attempt++) {
      await wh.locator('.o_data_row').first().locator('td[name="quantity"]').click();
      qcEditReady = await qcSelectedRow.locator('div[name="quantity"] input').isVisible().catch(() => false);
      if (!qcEditReady) {
        await wh.waitForTimeout(500);
      }
    }
    await qcSelectedRow.locator('div[name="quantity"] input').fill('40');
    const rejectedInput = qcSelectedRow.locator('div[name="dlm_qty_rejected"] input');
    await rejectedInput.fill('10');
    // "Lý do loại" chỉ hết readonly (required="dlm_qty_rejected > 0") SAU khi
    // ô Loại đã commit giá trị — Tab để blur trước khi động vào select.
    await rejectedInput.press('Tab');
    await qcSelectedRow.locator('div[name="dlm_reject_reason"] select')
      .selectOption({ label: 'Hàng lỗi / hư hỏng' });

    await wh.getByRole('button', { name: 'Xác nhận kiểm' }).click();
    await expect(wh.getByText('Đã cất').first()).toBeVisible({ timeout: 20000 });
    await expect(wh.locator('.alert-danger')).toHaveCount(0);

    // Smart button "Phiếu trả nhà cung cấp" phải hiện — bằng chứng phiếu trả
    // NCC đã tự sinh thật từ kết quả kiểm, không phải suy diễn.
    await expect(wh.getByRole('button', { name: /Phiếu trả nhà cung cấp/ })).toBeVisible({ timeout: 15000 });
    await whContext.close();

    // --- SCR-56: quay lại đúng màn danh sách qua rail của Mua hàng (không
    // bằng stat button) — xác nhận phiếu vừa sinh nằm đúng trên rail Mua
    // hàng, không phải chỉ mở được bằng đường tắt từ phiếu kiểm. ---
    await openPurchaseChild(page, 'Trả hàng nhà cung cấp');
    for (const col of ['Số phiếu', 'Nhà cung cấp', 'Phiếu nhận gốc', 'Số lượng trả', 'Lý do', 'Trạng thái']) {
      await expect(page.getByRole('columnheader', { name: col })).toBeVisible({ timeout: 15000 });
    }
    // Lọc đúng phiếu của lần chạy này bằng số phiếu nhận gốc — tránh trùng
    // với phiếu trả của những lần chạy test trước còn nằm lại ở nấc Nháp.
    await page.locator('.o_searchview_input').first().fill(receiptName);
    await page.locator('.o_searchview_input').first().press('Enter');
    const returnRow = page.getByRole('row', { name: new RegExp(SUPPLIER) });
    await expect(returnRow).toHaveCount(1, { timeout: 15000 });
    await expect(returnRow.getByRole('cell', { name: '10' })).toBeVisible();

    // --- SCR-57: mở đúng phiếu vừa lọc, chốt trả thật ---
    await returnRow.click();
    await expect(page.getByText('Trả hàng nhà cung cấp').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('cell', { name: '10' }).first()).toBeVisible();
    // Mua hàng có quyền Chốt trả hàng nhưng KHÔNG có quyền Xác nhận đã trả
    // (đó là việc vật lý của Thủ kho lúc xe NCC tới lấy hàng) — canh cả hai
    // chiều trên cùng một phiếu.
    await expect(page.getByRole('button', { name: 'Xác nhận đã trả' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Chốt trả hàng' }).click();
    await expect(page.locator('.alert-danger, .o_error_dialog')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Chốt trả hàng' })).toHaveCount(0);
  });
});

test.describe('Hỏi giá chờ trả lời - màn thật chưa có mã FDS (role: Mua hàng)', () => {
  test.use({ storageState: ROLES.mua_hang.storageStatePath });

  test('mở được qua rail, chỉ liệt kê đơn đã gửi hỏi giá và có báo giá nguồn', async ({ page }) => {
    await page.goto('/web');
    await openPurchaseChild(page, 'Hỏi giá chờ trả lời');
    await expect(page.getByText('Hỏi giá chờ trả lời').first()).toBeVisible({ timeout: 15000 });

    const rows = page.locator('.o_data_row');
    const count = await rows.count();
    if (count > 0) {
      // Domain thật của action_dl_purchase_rfq_queue: state=sent VÀ có
      // dlm_quotation_id — mọi dòng lọt vào đây phải đang ở nấc này.
      for (let i = 0; i < count; i++) {
        await expect(rows.nth(i).getByRole('cell', { name: 'Đã gửi hỏi giá' })).toBeVisible();
      }
    } else {
      await expect(page.getByText('Không có cuộc hỏi giá nào đang chờ')).toBeVisible();
    }
  });
});
