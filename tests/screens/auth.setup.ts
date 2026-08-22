import { test as setup } from '@playwright/test';
import { ROLES } from '../fixtures/roles';

for (const role of Object.values(ROLES)) {
  setup(`authenticate as ${role.label}`, async ({ page }) => {
    await page.goto('/web/login');
    await page.getByRole('textbox', { name: 'Tên đăng nhập' }).fill(role.login);
    await page.getByRole('textbox', { name: 'Mật khẩu' }).fill(role.password);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();

    // Đăng nhập thành công khi menu user (góc dưới trái) xuất hiện.
    // KHÔNG chờ URL cụ thể vì SCR-01 hiện KHÔNG điều hướng ổn định về Home Hub (SCR-35) — xem BUG-01 trong bug-log.md.
    await page.getByRole('button', { name: /Người dùng/ }).waitFor({ state: 'visible', timeout: 15000 });

    await page.context().storageState({ path: role.storageStatePath });
  });
}
