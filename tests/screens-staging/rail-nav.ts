import type { Page } from '@playwright/test';

// Rail (dl_base/static/src/components/rail/rail.js) toggleSubmenu() làm !expanded[key] — không
// phải "luôn mở". Nếu landing mặc định của role đã để mục cha ở trạng thái "đang mở" từ trước
// (vd Sales landing thẳng vào "Danh sách báo giá" dưới rail "Báo giá"), bấm 1 lần vào mục cha sẽ
// ĐÓNG submenu lại thay vì mở — khiến mục con không bao giờ xuất hiện. Helper này kiểm tra mục
// con đã hiện chưa trước khi bấm, và bấm lại lần 2 nếu lần đầu vô tình đóng mất.
export async function openRailChild(page: Page, parentTitle: string, childTitle: string) {
  const child = page.locator(`div[title="${childTitle}"]`);
  if (await child.isVisible().catch(() => false)) {
    return child;
  }
  // Toggle có thể cần bấm lẻ (mở) hoặc chẵn (đóng rồi mở lại) tuỳ trạng thái landing mặc định của
  // từng role — thử tối đa 3 lần, dừng ngay khi mục con xuất hiện.
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.getByTitle(parentTitle, { exact: true }).click();
    if (await child.isVisible({ timeout: 2500 }).catch(() => false)) {
      return child;
    }
  }
  await child.waitFor({ state: 'visible', timeout: 15000 });
  return child;
}
