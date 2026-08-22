// NFR-P03 [staging] — kiểm tra chịu tải 50-100 user đăng nhập + thao tác đồng thời (PRD §6.1).
// Đây là công cụ đo tải thật (k6), khác hẳn Playwright (chỉ mô phỏng 1 trình duyệt/lần).
//
// Chạy (PowerShell hoặc bash), KHÔNG hardcode mật khẩu vào file này:
//   $env:DLM_STAGING_PASSWORD="<mật khẩu thật>"; k6 run tests/load-staging/k6-concurrent-users.js
//   DLM_STAGING_PASSWORD=<mật khẩu thật> k6 run tests/load-staging/k6-concurrent-users.js
//
// Biến môi trường tuỳ chọn:
//   BASE_URL   (mặc định https://erp.dailinh.com)
//   DB         (mặc định dlm_prod)
//   MAX_VUS    (mặc định 100)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'https://erp.dailinh.com';
const DB = __ENV.DB || 'dlm_prod';
const PASSWORD = __ENV.DLM_STAGING_PASSWORD;
const MAX_VUS = parseInt(__ENV.MAX_VUS || '100', 10);

if (!PASSWORD) {
  throw new Error('Thiếu biến môi trường DLM_STAGING_PASSWORD — không hardcode mật khẩu vào script.');
}

// 8 tài khoản nghiệp vụ thật trên staging — xoay vòng giữa các VU để mô phỏng nhiều người dùng
// thật đăng nhập đồng thời (không phải 1 tài khoản gánh toàn bộ tải).
const ACCOUNTS = [
  'admin.it@gmail.com',
  'ceo@gmail.com',
  'truongkd@gmail.com',
  'ba@gmail.com',
  'kythuat@gmail.com',
  'ketoan@gmail.com',
  'thukho@gmail.com',
  'muahang@gmail.com',
];

const loginTrend = new Trend('dlm_login_duration');
const listTrend = new Trend('dlm_quotation_list_duration');
const openTrend = new Trend('dlm_quotation_open_duration');
const bomListTrend = new Trend('dlm_bom_list_duration');
const errorRate = new Rate('dlm_errors');

export const options = {
  scenarios: {
    concurrent_users: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: Math.round(MAX_VUS / 2) }, // ramp to 50
        { duration: '1m', target: Math.round(MAX_VUS / 2) },  // giữ 50 user 1 phút
        { duration: '30s', target: MAX_VUS },                 // ramp to 100
        { duration: '1m', target: MAX_VUS },                  // giữ 100 user 1 phút
        { duration: '30s', target: 0 },                       // ramp down
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    // NFR-P01: tải danh sách < 4s cho >=95% request
    dlm_quotation_list_duration: ['p(95)<4000'],
    // NFR-P02: mở chi tiết báo giá (tính giá) < 10s cho >=95% request
    dlm_quotation_open_duration: ['p(95)<10000'],
    // NFR-P01 (màn BOM, vai trò Kỹ thuật): < 4s cho >=95% request
    dlm_bom_list_duration: ['p(95)<4000'],
    dlm_errors: ['rate<0.05'],
    http_req_failed: ['rate<0.05'],
  },
};

function jsonRpc(path, method, params, jar) {
  const res = http.post(
    `${BASE_URL}${path}`,
    JSON.stringify({ jsonrpc: '2.0', method: 'call', params, id: Math.floor(Math.random() * 1e9) }),
    { headers: { 'Content-Type': 'application/json' }, jar }
  );
  return res;
}

export default function () {
  const login = ACCOUNTS[__VU % ACCOUNTS.length];
  const jar = http.cookieJar();

  // 1. Đăng nhập — /web/session/authenticate
  const loginStart = Date.now();
  const authRes = jsonRpc('/web/session/authenticate', 'authenticate', { db: DB, login, password: PASSWORD }, jar);
  loginTrend.add(Date.now() - loginStart);

  const authOk = check(authRes, {
    'đăng nhập thành công (200)': (r) => r.status === 200,
    'đăng nhập trả về uid': (r) => {
      try {
        return JSON.parse(r.body).result && JSON.parse(r.body).result.uid;
      } catch (e) {
        return false;
      }
    },
  });
  if (!authOk) {
    errorRate.add(1);
    sleep(1);
    return;
  }
  errorRate.add(0);

  sleep(1); // think time — mô phỏng người dùng thật đọc màn hình sau khi đăng nhập

  // 2. Tải Danh sách báo giá — search_read dl.quotation (NFR-P01)
  const listStart = Date.now();
  const listRes = jsonRpc(
    '/web/dataset/call_kw',
    'call',
    {
      model: 'dl.quotation',
      method: 'search_read',
      args: [[], ['name', 'partner_id', 'state', 'amount_total']],
      kwargs: { limit: 80 },
    },
    jar
  );
  listTrend.add(Date.now() - listStart);

  let quotationIds = [];
  const listOk = check(listRes, {
    'tải danh sách báo giá OK (200, không lỗi RPC)': (r) => {
      if (r.status !== 200) return false;
      try {
        const body = JSON.parse(r.body);
        if (body.error) return false;
        quotationIds = (body.result || []).map((rec) => rec.id);
        return true;
      } catch (e) {
        return false;
      }
    },
  });
  errorRate.add(listOk ? 0 : 1);

  sleep(1);

  // 3. Mở chi tiết 1 báo giá — read (NFR-P02, dữ liệu tính giá)
  if (quotationIds.length > 0) {
    const pickId = quotationIds[Math.floor(Math.random() * quotationIds.length)];
    const openStart = Date.now();
    const openRes = jsonRpc(
      '/web/dataset/call_kw',
      'call',
      {
        model: 'dl.quotation',
        method: 'read',
        args: [[pickId], ['name', 'partner_id', 'state', 'amount_total', 'line_ids']],
        kwargs: {},
      },
      jar
    );
    openTrend.add(Date.now() - openStart);

    const openOk = check(openRes, {
      'mở chi tiết báo giá OK (200, không lỗi RPC)': (r) => {
        if (r.status !== 200) return false;
        try {
          const body = JSON.parse(r.body);
          return !body.error;
        } catch (e) {
          return false;
        }
      },
    });
    errorRate.add(openOk ? 0 : 1);
  }

  sleep(1);

  // 4. Kỹ thuật: tải màn BOM sản phẩm (NFR-P01, đo riêng vì role khác không có quyền đọc dl.bom)
  if (login === 'kythuat@gmail.com') {
    const bomStart = Date.now();
    const bomRes = jsonRpc(
      '/web/dataset/call_kw',
      'call',
      {
        model: 'dl.bom',
        method: 'search_read',
        args: [[], ['name', 'product_id', 'status']],
        kwargs: { limit: 80 },
      },
      jar
    );
    bomListTrend.add(Date.now() - bomStart);
    const bomOk = check(bomRes, {
      'tải danh sách BOM OK (200, không lỗi RPC)': (r) => {
        if (r.status !== 200) return false;
        try {
          const body = JSON.parse(r.body);
          return !body.error;
        } catch (e) {
          return false;
        }
      },
    });
    errorRate.add(bomOk ? 0 : 1);
  }

  sleep(1 + Math.random() * 2); // think time ngẫu nhiên 1-3s giữa các vòng lặp
}
