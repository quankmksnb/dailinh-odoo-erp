import { test, expect } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

// TC-E2E-BF09-004 [staging] — kiểm tra lại đúng theo code hiện tại (dl_product/views/menus.xml):
// BA/Sales và CEO dùng CHUNG action_dl_product_view (context create:False/edit:False/delete:False,
// view-only thật). Trưởng phòng KD dùng RIÊNG action_dl_product_trading_ba (context create bình
// thường, tạo được sản phẩm thương mại) — khác hẳn mô tả cũ trong Report 5.3 ("CEO và Trưởng KD
// không có nút Mới"). Bấm rail 1 lần đôi khi chưa kịp điều hướng (menu cha cần mở trước) — bấm
// lại tới khi URL đổi đúng action, không dựa vào timeout cố định.
for (const [label, roleKey, expectNew] of [
  ['BA/Sales', 'sales', false],
  ['CEO', 'ceo', false],
  ['Trưởng KD', 'truong_kd', true],
] as const) {
  test(`TC-E2E-BF09-004 [staging]: ${label} mở danh sách Sản phẩm`, async ({ browser }) => {
    test.setTimeout(30000);
    const ctx = await browser.newContext({ storageState: STAGING_ROLES[roleKey].storageStatePath });
    const page = await ctx.newPage();
    await page.goto('/web');
    await page.waitForTimeout(1000);

    const child = page.locator('div[title="Sản phẩm"]');
    if (!(await child.isVisible().catch(() => false))) {
      await page.getByTitle('Sản phẩm & Vật tư', { exact: true }).click();
    }
    await child.first().waitFor({ state: 'visible', timeout: 10000 });

    let navigated = false;
    for (let i = 0; i < 5 && !navigated; i++) {
      await child.first().click();
      navigated = await page.waitForURL(/model=product\.product/, { timeout: 3000 }).then(() => true).catch(() => false);
    }
    expect(navigated, 'không điều hướng được tới màn Sản phẩm sau 5 lần bấm').toBe(true);

    const newBtn = page.getByRole('button', { name: /Mới/ });
    const hasNew = await newBtn.count() > 0 && await newBtn.first().isVisible().catch(() => false);
    console.log(`[staging] TC-E2E-BF09-004: ${label} thấy nút Mới = ${hasNew} (kỳ vọng ${expectNew})`);
    expect(hasNew).toBe(expectNew);
    await ctx.close();
  });
}
