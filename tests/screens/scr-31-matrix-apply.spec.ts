import { test, expect } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

// BF-06 Approval Rule Administration — TC-E2E-BF06-004: CEO là 1 trong 2 vai trò DUY
// NHẤT (cùng Admin) được "Áp dụng"/"Ngừng" dòng ma trận (pricing_matrix.py
// _is_matrix_manager()). Trước đây (scr-31-pricing-config.spec.ts) mới test tab
// "Hao hụt & thu hồi"; tab "Ma trận duyệt báo giá" (action=316) chưa test.
//
// Dùng luồng "Sửa đổi" (action_create_revision) trên 1 dòng ĐANG ÁP DỤNG thay vì tạo
// hẳn 1 ngưỡng mới: tạo mới rất dễ vi phạm ràng buộc "thang ngưỡng đơn điệu"
// (_assert_fits_ladder — mỗi cấp duyệt chỉ giữ 1 ngưỡng bắt đầu), vì dlm_dev đã có sẵn
// CEO ở ngưỡng cao nhất nên bất kỳ ngưỡng CEO mới nào cũng bị coi là "thừa". "Sửa đổi"
// tạo bản Nháp kế thừa đúng cấp duyệt của dòng gốc nên không đụng ràng buộc này, và
// đúng với đúng kịch bản FDS: CEO sửa/áp dụng 1 quy tắc đã Approved.
test.use({ storageState: ROLES.ceo.storageStatePath });

test.describe('SCR-31 - Ma trận duyệt báo giá (role: CEO) — Sửa đổi & Áp dụng', () => {
  test('CEO tạo bản sửa đổi từ 1 mức đang áp dụng rồi Áp dụng, trạng thái chuyển "Đang áp dụng"', async ({ page }) => {
    test.setTimeout(60000);
    await page.goto('/web#action=316&cids=1&menu_id=67');
    await expect(page.getByRole('button', { name: /Hao hụt & thu hồi/ })).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Phê duyệt' }).click();
    await page.getByRole('button', { name: 'Ma trận duyệt báo giá' }).click();
    await expect(page.getByText('Ma trận phê duyệt theo giá trị báo giá')).toBeVisible({ timeout: 15000 });

    // LƯU Ý: test này làm thay đổi dữ liệu thật (tạo 1 revision mới + Áp dụng) — chấp
    // nhận được, cùng tinh thần với scr-30-approval-flow.spec.ts (không rollback vì
    // Playwright E2E không chạy trong transaction như TransactionCase L2). Chạy lại
    // nhiều lần sẽ cộng dồn thêm revision trong lịch sử — vô hại, đúng bản chất tính
    // năng (mỗi lần Sửa đổi tạo 1 revision mới, bản cũ tự chuyển "Ngừng áp dụng").

    // Dòng "Trưởng kinh doanh" đang áp dụng (seed data dlm_dev có sẵn 20.000.000 đ).
    const activeRow = page
      .locator('tr')
      .filter({ hasText: 'Trưởng kinh doanh' })
      .filter({ hasText: 'Đang áp dụng' })
      .first();
    await expect(activeRow).toBeVisible({ timeout: 15000 });
    const revisionBefore = await activeRow.locator('td').nth(5).innerText();

    await activeRow.getByRole('button', { name: 'Sửa đổi' }).click();

    // "Sửa đổi" mở luôn form Nháp mới (pricing_config.js revise()).
    const formDialog = page.locator('.dl-pc-form');
    await expect(formDialog.getByText('Sửa quy tắc')).toBeVisible({ timeout: 15000 });
    // Bản sửa đổi (revision > 1) bắt buộc nhập Lý do thay đổi trước khi Áp dụng được.
    await formDialog.getByPlaceholder('Ghi lại để truy vết').fill(
      'System test QA: xác nhận CEO áp dụng được bản sửa đổi (TC-E2E-BF06-004)'
    );
    await formDialog.getByRole('button', { name: 'Lưu' }).click();
    await expect(formDialog).toBeHidden({ timeout: 15000 });

    // Dòng Nháp mới vừa tạo — bảng sắp theo "value_from asc, revision desc" (pricing_config.js
    // sortKey), nên bản Nháp MỚI tạo (revision cao nhất trong nhóm 20.000.000/Trưởng kinh
    // doanh) luôn nổi lên ĐẦU nhóm đó, bất kể chạy lại bao nhiêu lần — .first() ổn định
    // hơn lọc theo ngày (sẽ đụng chính dòng vừa Áp dụng ở lần chạy trước nếu lọc theo
    // "hôm nay"). Cùng 1 locator .first() vẫn đúng SAU khi Áp dụng vì thứ tự không đổi
    // theo state — chỉ cần bỏ điều kiện "Nháp" lúc đó.
    const groupRows = page
      .locator('tr')
      .filter({ hasText: 'Trưởng kinh doanh' })
      .filter({ hasText: '20.000.000' });
    const draftRow = groupRows.filter({ hasText: 'Nháp' }).first();
    await expect(draftRow).toBeVisible({ timeout: 15000 });
    const newRevision = await draftRow.locator('td').nth(5).innerText();
    expect(newRevision).not.toBe(revisionBefore);

    await draftRow.getByRole('button', { name: 'Áp dụng' }).click();

    // Áp dụng thành công: dòng vừa Sửa đổi (vẫn xếp đầu nhóm, revision cao nhất) chuyển
    // "Đang áp dụng"; bản gốc tự đóng lại thành "Ngừng áp dụng".
    const appliedRow = groupRows.first();
    await expect(appliedRow.getByText('Đang áp dụng')).toBeVisible({ timeout: 15000 });
    expect(await appliedRow.locator('td').nth(5).innerText()).toBe(newRevision);
  });
});
