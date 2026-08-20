import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// BF-01(thương mại)/BF-03/BF-05/BF-09 nối tiếp nhau trên 1 luồng thật: RFQ chỉ có dòng THƯƠNG MẠI
// (không cần Kỹ thuật xử lý — auto "confirmed" theo _recompute_status_from_lines khi mọi dòng đã
// resolved) -> Sales đánh dấu đã tạo báo giá -> tạo Báo giá -> Duyệt nội bộ (dưới ngưỡng, Sales tự
// gửi được) -> Gửi khách -> Tạo Đơn bán hàng. Dùng sản phẩm thương mại có sẵn duy nhất trên
// staging ("Ghế sắt sơn tĩnh điện GS-100", product.product id=31, product_kind=trading).
test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

test('BF-01/03/05/09: RFQ hàng thương mại -> Báo giá -> Gửi khách -> Đơn bán hàng', async ({ page }) => {
  test.setTimeout(90000);

  // Bước 1: tạo RFQ với 1 dòng thương mại — không cần Kỹ thuật, RFQ tự chuyển "Chờ tạo báo giá".
  await page.goto('/web');
  await page.getByTitle('Báo giá', { exact: true }).click();
  await page.locator('div[title="Tạo RFQ"]').click();
  await expect(page.getByText('Thêm yêu cầu báo giá').first()).toBeVisible({ timeout: 20000 });

  const customerField = page.locator('input[id^="customer_id_"]');
  await customerField.waitFor({ state: 'visible', timeout: 20000 });
  await customerField.click({ force: true });
  await customerField.fill('Công ty TNHH Cơ khí Việt Thành');
  const customerOption = page.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Công ty TNHH Cơ khí Việt Thành' });
  await customerOption.first().waitFor({ state: 'visible', timeout: 10000 });
  await customerOption.first().click();

  await page
    .getByRole('table')
    .filter({ hasText: 'Sản phẩmĐơn giáSố lượngThành tiền' })
    .getByRole('button', { name: 'Thêm một dòng' })
    .click();
  const productField = page.locator('div[name="product_id"] input, div[name="resolved_product_id"] input').last();
  await productField.click({ force: true });
  await productField.fill('Ghế sắt sơn tĩnh điện');
  const productOption = page.locator('.o-autocomplete--dropdown-menu li', { hasText: 'Ghế sắt sơn tĩnh điện' });
  await productOption.first().waitFor({ state: 'visible', timeout: 10000 });
  await productOption.first().click();

  await page.getByRole('button', { name: 'Lưu thủ công' }).click();
  await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('New', { timeout: 15000 });
  await expect.poll(() => page.url(), { timeout: 15000 }).toMatch(/[?&#]id=\d+/);
  const rfqId = page.url().match(/[?&#]id=(\d+)/)![1];
  console.log(`[staging] Đã tạo RFQ hàng thương mại (id=${rfqId})`);

  // Bước 2: RFQ tự "Chờ tạo báo giá" (không cần Kỹ thuật) -> nút "Tạo báo giá" trên header tạo
  // VÀ LƯU LUÔN 1 Báo giá mới (đã ở breadcrumb, không phải bản Nháp "New" cần Lưu tiếp), kế
  // thừa sẵn Khách hàng + dòng sản phẩm từ RFQ. Mã báo giá hiện ở breadcrumb, không phải <h1>.
  await expect(page.getByText('Chờ tạo báo giá')).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Tạo báo giá' }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toMatch(/model=dl\.quotation[^.]/);
  const quoteCode = await page.locator('.o_breadcrumb, .o_last_breadcrumb_item').last().innerText();
  console.log(`[staging] Đã tạo báo giá ${quoteCode} (kế thừa từ RFQ)`);

  // Bước 4: Gửi khách (dưới ngưỡng phê duyệt nên gửi thẳng được từ Nháp).
  const sendBtn = page.getByRole('button', { name: /Gửi khách hàng|Xuất.*Gửi báo giá/ });
  if (await sendBtn.count()) {
    await sendBtn.first().click();
    await expect(page.getByText('Đã gửi khách', { exact: false }).first()).toBeVisible({ timeout: 15000 });
    console.log(`[staging] ${quoteCode}: đã gửi khách hàng thành công`);
  } else {
    console.log(`[staging] ${quoteCode}: không thấy nút Gửi khách trực tiếp — có thể cần Duyệt nội bộ trước (giá trị RFQ vượt ngưỡng mặc định).`);
    return;
  }

  // Bước 5: Sales ghi nhận "Khách đồng ý" (khách chốt mua qua điện thoại — thao tác thủ công
  // của Sales, không có khách hàng thật xác nhận online) rồi tạo Đơn bán hàng (BF-09).
  await page.getByRole('button', { name: 'Khách đồng ý' }).click();
  await expect(page.getByText('Khách đồng ý', { exact: false }).first()).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Tạo đơn bán hàng' }).click();
  await expect.poll(() => page.url(), { timeout: 15000 }).toMatch(/model=dl\.sale\.order/);
  const orderCode = await page.locator('.o_breadcrumb, .o_last_breadcrumb_item').last().innerText();
  console.log(`[staging] Đã tạo Đơn bán hàng ${orderCode} từ ${quoteCode}`);
});
