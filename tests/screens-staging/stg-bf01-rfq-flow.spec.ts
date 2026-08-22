import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// Smoke-test BF-01 trên bản đã deploy (https://erp.dailinh.com, db dlm_prod). Database này gần
// như trống (chưa chạy seed_qa_data.py — 0 RFQ, 10 partner, không có khách hàng loại customer
// nào) nên không thể tái dùng ID bản ghi có sẵn như bộ test dlm_dev — phải tự tạo dữ liệu mới.
//
// Tạo khách hàng qua màn "Khách hàng" riêng (form đầy đủ trên 1 trang) THAY VÌ qua dialog
// "Tạo nhanh" bật lên từ ô tìm kiếm trong form RFQ: dialog đó không tự điền lại tên đã gõ ở ô
// tìm kiếm (field "Tên khách hàng" trống, bắt buộc) và nút "Lưu & Đóng" không bắn RPC nào khi
// dialog lồng trong dialog khác — tránh hẳn 2 vấn đề đó bằng cách tạo khách hàng trước, độc lập.
test('BF-01: Sales tạo khách hàng + RFQ mới -> Kỹ thuật nhận và xử lý', async ({ browser }) => {
  test.setTimeout(90000);
  const salesCtx = await browser.newContext({ storageState: STAGING_ROLES.sales.storageStatePath });
  const salesPage = await salesCtx.newPage();

  // Bước 1: tạo khách hàng qua màn riêng (form đầy đủ, không phải dialog lồng).
  await salesPage.goto('/web');
  await salesPage.getByTitle('Khách hàng', { exact: true }).click();
  await salesPage.getByRole('button', { name: /Mới|Tạo|New/ }).first().click();

  const uniqueSuffix = Date.now().toString().slice(-7);
  const customerName = 'Công ty TNHH Cơ khí Việt Thành';
  await salesPage.locator('div[name="name"] input, div[name="name"] textarea').first().fill(customerName);
  await salesPage.getByLabel('Điện thoại', { exact: true }).fill(`090${uniqueSuffix}`);
  // MST bắt buộc với Doanh nghiệp/Đại lý — label có icon tooltip nên không getByLabel khớp
  // chính xác, dùng placeholder.
  const vatField = salesPage.getByPlaceholder(/Bắt buộc với Doanh nghiệp/);
  if (await vatField.count()) {
    await vatField.fill(`031${uniqueSuffix}`);
  }
  // Doanh nghiệp cũng bắt buộc Đường + Tỉnh/Thành phố (2 field ẩn không có dấu * rõ ràng trên
  // UI nhưng vẫn chặn lưu nếu trống — phát hiện qua .o_required_modifier còn rỗng).
  await salesPage.getByPlaceholder('Số nhà, tên đường...').fill('123 Đường Nguyễn Văn Linh');
  await salesPage.getByPlaceholder('Tỉnh / Thành phố').fill('TP. Hồ Chí Minh');
  // Quốc gia — many2one autocomplete, phải chọn từ dropdown (fill() text không đủ để set giá trị).
  const countryField = salesPage.getByPlaceholder('Quốc gia');
  await countryField.click();
  await countryField.fill('Việt Nam');
  const countryOption = salesPage.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Việt Nam' });
  await countryOption.first().waitFor({ state: 'visible', timeout: 10000 });
  await countryOption.first().click();
  // Quốc gia trống là nguyên nhân "Lưu thủ công" không bắn RPC nào cả (chặn validate phía
  // client, hoàn toàn im lặng — không class .o_field_invalid, không toast lỗi) — phát hiện qua
  // debug .o_required_modifier còn field "country_id" rỗng dù mọi field khác đã điền đủ.
  await salesPage.getByRole('button', { name: 'Lưu thủ công' }).click();
  // Màn Khách hàng không dùng <h1> cho tên (khác RFQ/BOM) — chờ breadcrumb đổi từ
  // "Thêm khách hàng" sang tên bản ghi vừa lưu.
  await expect(salesPage.getByText('Thêm khách hàng')).toBeHidden({ timeout: 15000 });
  await expect(salesPage.locator('.o_breadcrumb, .o_last_breadcrumb_item').getByText(customerName))
    .toBeVisible({ timeout: 10000 });

  // Bước 2: tạo RFQ, chọn lại đúng khách hàng vừa tạo (không dùng flow "Tạo" nữa).
  await salesPage.getByTitle('Báo giá', { exact: true }).click();
  // Rail bên trái mở ra danh sách link (không phải ARIA menuitem) — bấm vào div cha
  // (title="Tạo RFQ"), span con bị chính div cha chặn pointer-events.
  await salesPage.locator('div[title="Tạo RFQ"]').click();
  await expect(salesPage.getByText('Thêm yêu cầu báo giá').first()).toBeVisible({ timeout: 20000 });

  const customerField = salesPage.locator('input[id^="customer_id_"]');
  await customerField.waitFor({ state: 'visible', timeout: 20000 });
  await customerField.click({ force: true });
  await customerField.fill(customerName);
  const customerOption = salesPage.locator('.o-autocomplete--dropdown-menu li', { hasText: customerName });
  await customerOption.first().waitFor({ state: 'visible', timeout: 10000 });
  await customerOption.first().click();

  await salesPage
    .getByRole('table')
    .filter({ hasText: 'Tên sản phẩmNhóm sản phẩmSản' })
    .getByRole('button', { name: 'Thêm một dòng' })
    .click();
  await salesPage.getByRole('textbox', { name: 'Tên sản phẩm' }).fill('Cửa sắt hộp 40x40, sơn tĩnh điện');
  // Nhóm sản phẩm (product_category_id) nay là field bắt buộc trên dòng gia công
  // (quotation_request_views.xml, required="1") — chưa có lúc file này được viết. Label không
  // gắn aria-label vào input nên trỏ thẳng theo field name, giống stg-bf01-list-and-a5.spec.ts.
  const categoryField = salesPage.locator('[name="product_category_id"] input');
  await categoryField.click({ force: true });
  await categoryField.fill('Khung thép hàn');
  const categoryOption = salesPage.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Khung thép hàn' });
  await categoryOption.first().waitFor({ state: 'visible', timeout: 10000 });
  await categoryOption.first().click();
  // Placeholder trường mô tả (field dimension_note) đã đổi thành "Chi tiết khác: cao ghế,
  // khổ mặt ghế, màu sơn, yêu cầu riêng..." — không còn tên "Kích thước, yêu cầu kỹ thuật" nữa.
  await salesPage.locator('[name="dimension_note"] textarea, textarea[name="dimension_note"]')
    .fill('Kích thước 1200x2000mm, khung hộp 40x40x1.5mm, sơn tĩnh điện màu ghi');
  // "Lưu & Đóng" khớp cả nút của dialog dòng sản phẩm lẫn nút Lưu chính của form phía sau
  // (dialog đang mở) — chỉ bấm đúng nút bên trong dialog.
  await salesPage.locator('.modal, [role="dialog"]').last()
    .getByRole('button', { name: 'Lưu & Đóng' }).click();
  await salesPage.getByRole('button', { name: 'Lưu thủ công' }).click();

  await expect(salesPage.getByRole('heading', { level: 1 })).not.toHaveText('New', { timeout: 15000 });
  await expect.poll(() => salesPage.url(), { timeout: 15000 }).toMatch(/[?&#]id=\d+/);
  const idMatch = salesPage.url().match(/[?&#]id=(\d+)/);
  const rfqId = idMatch![1];
  const rfqCode = await salesPage.getByRole('heading', { level: 1 }).innerText();
  console.log(`[staging] Đã tạo RFQ ${rfqCode} (id=${rfqId})`);
  await salesCtx.close();

  // Bước 3: Kỹ thuật mở RFQ vừa tạo, xác nhận nhận được đúng luồng xử lý.
  const kythuatCtx = await browser.newContext({ storageState: STAGING_ROLES.ky_thuat.storageStatePath });
  const page = await kythuatCtx.newPage();
  await page.goto(`/web#id=${rfqId}&model=dl.quotation.request&view_type=form`);
  await expect(page.getByText(/RFQ này chưa được nhận xử lý|Đang xử lý/).first()).toBeVisible({ timeout: 15000 });
  await kythuatCtx.close();
});
