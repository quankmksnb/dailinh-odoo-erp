import { test as setup } from '@playwright/test';
import { STAGING_ROLES } from '../fixtures/roles.staging';

for (const role of Object.values(STAGING_ROLES)) {
  setup(`[staging] authenticate as ${role.label}`, async ({ page }) => {
    await page.goto('/web/login');
    await page.getByRole('textbox', { name: /Tên đăng nhập|Email/ }).fill(role.login);
    await page.getByRole('textbox', { name: 'Mật khẩu' }).fill(role.password);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();

    await page.getByRole('button', { name: /Người dùng|Admin|CEO|Sales|Kỹ thuật|Kế toán|Thủ kho|Mua hàng/ })
      .first().waitFor({ state: 'visible', timeout: 20000 });

    await page.context().storageState({ path: role.storageStatePath });
  });
}
