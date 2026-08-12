import { test, chromium } from '@playwright/test';
import fs from 'fs';

// Đo NFR-P01 (tải trang < 4s) và NFR-P02 (phản hồi tính giá < 10s) theo PRD §6.1, bằng
// Playwright thật (không mock), môi trường dev 1 user (không có 50-100 user đồng thời như
// PRD mô tả — ghi rõ điều kiện đo khác PRD trong kết quả, không tự nhận là đã đo đúng tải PRD).
const BASE_URL = process.env.DLM_BASE_URL || 'http://127.0.0.1:8069';
const results: Record<string, number> = {};

test('Đo thời gian tải trang & phản hồi tính giá (ghi kết quả ra file JSON)', async () => {
  test.setTimeout(120000);
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // Login trước (không tính vào NFR-P01, chỉ là bước chuẩn bị).
  await page.goto(`${BASE_URL}/web/login`);
  await page.getByRole('textbox', { name: 'Tên đăng nhập' }).fill('sales1@dlm.demo');
  await page.getByRole('textbox', { name: 'Mật khẩu' }).fill('Demo@2026');
  await page.getByRole('textbox', { name: 'Mật khẩu' }).press('Enter');
  await page.waitForTimeout(1500);

  async function measure(label: string, url: string, waitText: string) {
    const t0 = Date.now();
    await page.goto(url);
    await page.getByText(waitText).first().waitFor({ state: 'visible', timeout: 15000 });
    results[label] = (Date.now() - t0) / 1000;
  }

  await measure('NFR-P01_list_baogia', `${BASE_URL}/web#action=295&model=dl.quotation&view_type=list&cids=1`, 'BG/');
  await measure('NFR-P01_list_bom', `${BASE_URL}/web#action=319&model=dl.bom&view_type=list&cids=1`, 'BOM-');
  await measure('NFR-P01_list_rfq', `${BASE_URL}/web#action=321&model=dl.quotation.request&view_type=list&cids=1`, 'RFQ-');

  // NFR-P02: mở chi tiết 1 báo giá đã có sẵn dòng + cấu phần giá — proxy cho "phản hồi tính giá"
  // (đo thời gian server trả về đầy đủ dữ liệu tính giá khi mở form, không phải lúc gõ sửa).
  const t0 = Date.now();
  await page.goto(`${BASE_URL}/web#action=295&model=dl.quotation&view_type=form&id=27&cids=1`);
  await page.getByText('Tổng thanh toán').first().waitFor({ state: 'visible', timeout: 15000 });
  results['NFR-P02_open_quotation_with_pricing'] = (Date.now() - t0) / 1000;

  await browser.close();

  fs.writeFileSync(
    'tests/reports/perf-results.json',
    JSON.stringify(results, null, 2),
    'utf-8',
  );
  console.log('PERF RESULTS:', JSON.stringify(results));
});
