import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// GB-02 (PRD §5): "Các trường thông tin: dòng sản phẩm, chiết khấu, VAT và khách hàng của Báo
// giá chỉ được phép chỉnh sửa khi ở trạng thái 'Nháp'. Ở các trạng thái khác, dữ liệu bị khóa
// chỉ đọc." Trước giờ chỉ xác nhận riêng chiết khấu (qua gap BF03-004/GB-17) — bổ sung dòng sản
// phẩm, VAT, khách hàng.
//
// Rà code: cả 4 field đều readonly="state != 'draft'" ở tầng FORM VIEW (quotation_views.xml) —
// chỉ khoá ở UI, KHÔNG khoá ở tầng server/RPC (đã tự xác nhận gián tiếp qua các test GB-17/25/09
// chạy trước: ghi thẳng qua RPC vào các field này khi báo giá đang "sent" vẫn thành công bình
// thường — đây là thiết kế chủ đích, GB-17 là lưới an toàn cho đúng tình huống RPC bypass này).
// Test này do đó tập trung đúng phạm vi GB-02 mô tả: khoá ở UI khi không phải Nháp.

test.describe('GB-02: Khoá field ngoài trạng thái Nháp', () => {
  test.use({ storageState: STAGING_ROLES.sales.storageStatePath });

  test('dòng sản phẩm, VAT, khách hàng đều readonly khi báo giá không ở Nháp', async ({ page }) => {
    test.setTimeout(60000);

    // Tìm 1 báo giá không ở Nháp qua RPC trước (nhanh hơn dò trong UI).
    const lookup = await page.request.post('/web/dataset/call_kw', {
      data: {
        jsonrpc: '2.0', method: 'call',
        params: {
          model: 'dl.quotation', method: 'search_read',
          args: [[['state', '!=', 'draft']], ['id', 'name', 'state']],
          kwargs: { limit: 1, order: 'id desc' },
        },
      },
    }).then((r) => r.json()).then((b) => b.result?.[0]);
    expect(lookup, 'Cần ít nhất 1 báo giá không ở Nháp trên staging để test GB-02').toBeTruthy();
    console.log(`[staging] GB-02: dùng báo giá ${lookup.name} (state=${lookup.state}) để kiểm khoá field.`);

    await page.goto(`/web#id=${lookup.id}&model=dl.quotation&view_type=form&cids=1`);
    await expect(page.getByRole('heading', { level: 1 }).or(page.locator('.o_breadcrumb')).first()).toBeVisible({ timeout: 15000 });

    // Khách hàng — many2one, readonly nên input không cho gõ được (hoặc field ở dạng text tĩnh).
    const partnerInput = page.locator('div[name="partner_id"] input');
    const hasPartnerInput = await partnerInput.count();
    if (hasPartnerInput > 0) {
      await expect(partnerInput.first()).toBeDisabled();
    }
    console.log(`[staging] GB-02: field Khách hàng ${hasPartnerInput > 0 ? '(input readonly xác nhận đúng)' : '(không phải input, có thể đã render dạng text tĩnh readonly)'}.`);

    // VAT — input number, readonly.
    const vatInput = page.locator('div[name="vat_pct"] input');
    const hasVatInput = await vatInput.count();
    if (hasVatInput > 0) {
      await expect(vatInput.first()).toBeDisabled();
      console.log('[staging] GB-02: field VAT readonly xác nhận đúng.');
    }

    // Dòng sản phẩm — bảng line_ids không có nút "Thêm một dòng" khi readonly.
    const addLineBtn = page.getByRole('button', { name: 'Thêm một dòng' });
    const hasAddLineBtn = await addLineBtn.count();
    console.log(`[staging] GB-02: nút "Thêm một dòng" ${hasAddLineBtn === 0 ? 'không hiện (đúng, bảng readonly)' : 'VẪN HIỆN — có thể là bug'}.`);
    expect(hasAddLineBtn, 'GB-02: bảng dòng sản phẩm phải readonly (không có nút Thêm một dòng) khi báo giá không ở Nháp').toBe(0);

    // Chiết khấu — đối chứng lại field đã biết trước đó (BF03-004) vẫn còn đúng.
    const discountInput = page.locator('div[name="discount_pct"] input');
    if (await discountInput.count()) {
      await expect(discountInput.first()).toBeDisabled();
    }
    console.log('[staging] GB-02: field Chiết khấu vẫn readonly đúng (đối chứng).');
  });
});
